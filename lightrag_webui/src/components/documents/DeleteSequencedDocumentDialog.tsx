import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import Button from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/Dialog'
import { toast } from 'sonner'
import { errorMessage, cn } from '@/lib/utils'
import { deleteSequencedDocument, replaceSequencedDocument, DocStatusResponse } from '@/api/lightrag'

import { TrashIcon, AlertTriangleIcon, Upload, FileText, X, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'

// Simple Label component
const Label = ({
  htmlFor,
  className,
  children,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) => (
  <label
    htmlFor={htmlFor}
    className={className}
    {...props}
  >
    {children}
  </label>
)

interface DocumentWithMetadata {
  file: File
  effectiveDate?: string
  sequenceIndex?: number
  id: string
}

interface DeleteSequencedDocumentDialogProps {
  document: DocStatusResponse | DocumentWithMetadata
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleteSuccess: () => void
  mode: 'existing' | 'pre-upload'
}

export default function DeleteSequencedDocumentDialog({
  document,
  open,
  onOpenChange,
  onDeleteSuccess,
  mode
}: DeleteSequencedDocumentDialogProps) {
  const { t } = useTranslation()
  const [replaceMode, setReplaceMode] = useState(false)
  const [replacementFile, setReplacementFile] = useState<File | null>(null)
  const [deleteFile, setDeleteFile] = useState(true)
  const [deleteLLMCache, setDeleteLLMCache] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)

  // Extract document info based on mode
  const getDocumentInfo = () => {
    if (mode === 'existing') {
      const doc = document as DocStatusResponse
      const metadata = doc.metadata || {}
      return {
        id: doc.id,
        fileName: doc.file_path?.split('/').pop() || doc.id,
        sequenceIndex: metadata.sequence_index,
        effectiveDate: metadata.date || metadata.effective_date,
        docType: metadata.doc_type
      }
    } else {
      const doc = document as DocumentWithMetadata
      return {
        id: doc.id,
        fileName: doc.file.name,
        sequenceIndex: doc.sequenceIndex,
        effectiveDate: doc.effectiveDate,
        docType: 'unknown'
      }
    }
  }

  const docInfo = getDocumentInfo()

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setReplaceMode(false)
      setReplacementFile(null)
      setDeleteFile(true)
      setDeleteLLMCache(false)
      setIsProcessing(false)
      setUploadProgress(0)
    }
  }, [open])

  // File upload handler
  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setReplacementFile(acceptedFiles[0])
      toast.success(t('sequencer.fileSelected', `Selected: ${acceptedFiles[0].name}`))
    }
  }, [t])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/markdown': ['.md']
    },
    multiple: false,
    disabled: isProcessing
  })

  const handleDelete = useCallback(async () => {
    if (mode === 'pre-upload') {
      // For pre-upload mode, just call the success callback
      onDeleteSuccess()
      onOpenChange(false)
      toast.success(t('sequencer.documentRemoved', 'Document removed from upload queue'))
      return
    }

    // For existing documents, call the API
    setIsProcessing(true)
    try {
      const result = await deleteSequencedDocument(
        docInfo.id,
        deleteFile,
        deleteLLMCache
      )

      toast.success(
        t('sequencer.deleteSuccess', 
          `Deleted document at position ${result.sequence_index}. Sequence gaps preserved.`
        )
      )

      onDeleteSuccess()
      onOpenChange(false)
    } catch (err) {
      toast.error(t('sequencer.deleteError', `Failed to delete: ${errorMessage(err)}`))
    } finally {
      setIsProcessing(false)
    }
  }, [mode, docInfo.id, deleteFile, deleteLLMCache, onDeleteSuccess, onOpenChange, t])

  const handleReplace = useCallback(async () => {
    if (!replacementFile) {
      toast.error(t('sequencer.noFileSelected', 'Please select a replacement file'))
      return
    }

    if (mode === 'pre-upload') {
      toast.error(t('sequencer.replaceNotAvailable', 'Replace is only available for uploaded documents'))
      return
    }

    setIsProcessing(true)
    setUploadProgress(0)

    try {
      const result = await replaceSequencedDocument(
        docInfo.id,
        replacementFile,
        (progress) => setUploadProgress(progress)
      )

      toast.success(
        t('sequencer.replaceSuccess',
          `Replaced document with ${result.new_file}. Preserved sequence ${result.preserved_metadata.sequence_index}.`
        )
      )

      onDeleteSuccess()
      onOpenChange(false)
    } catch (err) {
      toast.error(t('sequencer.replaceError', `Failed to replace: ${errorMessage(err)}`))
    } finally {
      setIsProcessing(false)
      setUploadProgress(0)
    }
  }, [replacementFile, mode, docInfo.id, onDeleteSuccess, onOpenChange, t])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" onCloseAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-500 dark:text-red-400 font-bold">
            <AlertTriangleIcon className="h-5 w-5" />
            {replaceMode 
              ? t('sequencer.replaceDocument', 'Replace Sequenced Document')
              : t('sequencer.deleteDocument', 'Delete Sequenced Document')
            }
          </DialogTitle>
          <DialogDescription className="pt-2">
            {replaceMode
              ? t('sequencer.replaceDescription', 'Upload a new file to replace this document while preserving its sequence position.')
              : t('sequencer.deleteDescription', 'Remove this document from the sequence. Other documents will maintain their positions (gaps allowed).')
            }
          </DialogDescription>
        </DialogHeader>

        {/* Document Info */}
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">File:</span>
            <span className="text-sm text-gray-900 dark:text-gray-100 font-mono">{docInfo.fileName}</span>
          </div>
          {docInfo.sequenceIndex !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Sequence:</span>
              <span className="text-sm text-emerald-600 dark:text-emerald-400 font-bold">#{docInfo.sequenceIndex}</span>
            </div>
          )}
          {docInfo.effectiveDate && (
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Effective Date:</span>
              <span className="text-sm text-gray-900 dark:text-gray-100">{docInfo.effectiveDate}</span>
            </div>
          )}
          {docInfo.docType && (
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Type:</span>
              <span className="text-sm text-gray-900 dark:text-gray-100 capitalize">{docInfo.docType}</span>
            </div>
          )}
        </div>

        {/* Replace Mode Toggle */}
        {mode === 'existing' && !isProcessing && (
          <div className="flex items-center justify-center gap-2 py-2">
            <Button
              variant={!replaceMode ? 'default' : 'outline'}
              size="sm"
              onClick={() => setReplaceMode(false)}
            >
              <TrashIcon className="h-4 w-4 mr-2" />
              Delete Only
            </Button>
            <Button
              variant={replaceMode ? 'default' : 'outline'}
              size="sm"
              onClick={() => setReplaceMode(true)}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Replace
            </Button>
          </div>
        )}

        {/* Replace File Upload */}
        {replaceMode && (
          <div className="space-y-3">
            <div
              {...getRootProps()}
              className={cn(
                'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all',
                isDragActive
                  ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950'
                  : 'border-gray-300 dark:border-gray-600 hover:border-emerald-400 dark:hover:border-emerald-500'
              )}
            >
              <input {...getInputProps()} />
              <Upload className={cn(
                "h-10 w-10 mx-auto mb-2",
                isDragActive ? "text-emerald-500" : "text-gray-400"
              )} />
              <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                {isDragActive
                  ? t('sequencer.dropFile', 'Drop file here...')
                  : t('sequencer.selectReplacement', 'Click or drag file to replace')}
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {t('sequencer.supportedFormats', 'TXT, PDF, DOC, DOCX, MD')}
              </p>
            </div>

            {replacementFile && (
              <div className="flex items-center justify-between p-3 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-lg">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
                    {replacementFile.name}
                  </span>
                  <span className="text-xs text-emerald-600 dark:text-emerald-400">
                    ({(replacementFile.size / 1024).toFixed(1)} KB)
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setReplacementFile(null)}
                  disabled={isProcessing}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}

            {isProcessing && uploadProgress > 0 && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-400">Uploading...</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium">{uploadProgress}%</span>
                </div>
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-emerald-600 dark:bg-emerald-400 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Delete Options */}
        {!replaceMode && mode === 'existing' && (
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="delete-file"
                checked={deleteFile}
                onChange={(e) => setDeleteFile(e.target.checked)}
                disabled={isProcessing}
                className="h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
              />
              <Label htmlFor="delete-file" className="text-sm font-medium cursor-pointer">
                {t('documentPanel.deleteDocuments.deleteFileOption', 'Also delete physical file')}
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="delete-llm-cache"
                checked={deleteLLMCache}
                onChange={(e) => setDeleteLLMCache(e.target.checked)}
                disabled={isProcessing}
                className="h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
              />
              <Label htmlFor="delete-llm-cache" className="text-sm font-medium cursor-pointer">
                {t('documentPanel.deleteDocuments.deleteLLMCacheOption', 'Also delete LLM cache')}
              </Label>
            </div>
          </div>
        )}

        {/* Warning */}
        {!replaceMode && (
          <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
            <p className="text-sm text-amber-800 dark:text-amber-200">
              <strong>Note:</strong> Sequence gaps will be preserved. For example, if you delete position #2, 
              the sequence will be: 1, 3, 4, 5...
            </p>
          </div>
        )}

        <DialogFooter>
          <Button 
            variant="outline" 
            onClick={() => onOpenChange(false)} 
            disabled={isProcessing}
          >
            {t('common.cancel', 'Cancel')}
          </Button>
          {replaceMode ? (
            <Button
              variant="default"
              onClick={handleReplace}
              disabled={!replacementFile || isProcessing}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {isProcessing ? t('sequencer.replacing', 'Replacing...') : t('sequencer.replaceButton', 'Replace Document')}
            </Button>
          ) : (
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isProcessing}
            >
              {isProcessing ? t('sequencer.deleting', 'Deleting...') : t('sequencer.deleteButton', 'Delete Document')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Made with Bob
