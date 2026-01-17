import { useState, useCallback } from 'react'
import Button from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/utils'
import { uploadDocument } from '@/api/lightrag'
import { UploadIcon, ChevronUp, ChevronDown, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface StagedFile {
  file: File
  sequenceIndex: number
}

interface StagingAreaDialogProps {
  onDocumentsUploaded?: () => Promise<void>
}

export default function StagingAreaDialog({ onDocumentsUploaded }: StagingAreaDialogProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgresses, setUploadProgresses] = useState<Record<string, number>>({})

  // Handle file selection
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    const newStagedFiles: StagedFile[] = files.map((file, index) => ({
      file,
      sequenceIndex: stagedFiles.length + index + 1
    }))

    setStagedFiles([...stagedFiles, ...newStagedFiles])
  }, [stagedFiles])

  // Move file up in sequence
  const moveUp = useCallback((index: number) => {
    if (index === 0) return
    const newFiles = [...stagedFiles]
    ;[newFiles[index - 1], newFiles[index]] = [newFiles[index], newFiles[index - 1]]
    // Update sequence indices
    newFiles.forEach((file, idx) => {
      file.sequenceIndex = idx + 1
    })
    setStagedFiles(newFiles)
  }, [stagedFiles])

  // Move file down in sequence
  const moveDown = useCallback((index: number) => {
    if (index === stagedFiles.length - 1) return
    const newFiles = [...stagedFiles]
    ;[newFiles[index], newFiles[index + 1]] = [newFiles[index + 1], newFiles[index]]
    // Update sequence indices
    newFiles.forEach((file, idx) => {
      file.sequenceIndex = idx + 1
    })
    setStagedFiles(newFiles)
  }, [stagedFiles])

  // Remove file from staging
  const removeFile = useCallback((index: number) => {
    const newFiles = stagedFiles.filter((_, idx) => idx !== index)
    // Update sequence indices
    newFiles.forEach((file, idx) => {
      file.sequenceIndex = idx + 1
    })
    setStagedFiles(newFiles)
  }, [stagedFiles])

  // Process staged files
  const handleProcessFiles = useCallback(async () => {
    if (stagedFiles.length === 0) {
      toast.error('No files to process')
      return
    }

    setIsUploading(true)
    let hasSuccessfulUpload = false

    const toastId = toast.loading(`Processing ${stagedFiles.length} file(s) in sequence...`)

    try {
      // Upload files in sequence order
      for (const stagedFile of stagedFiles) {
        const { file, sequenceIndex } = stagedFile

        try {
          // Initialize progress
          setUploadProgresses(prev => ({
            ...prev,
            [file.name]: 0
          }))

          // Upload with metadata
          const result = await uploadDocument(
            file,
            (percentCompleted: number) => {
              setUploadProgresses(prev => ({
                ...prev,
                [file.name]: percentCompleted
              }))
            },
            {
              sequence_index: sequenceIndex,
              effective_date: 'unknown', // User can enhance this later
              doc_type: sequenceIndex === 1 ? 'base' : 'amendment'
            }
          )

          if (result.status === 'success') {
            hasSuccessfulUpload = true
          } else if (result.status === 'duplicated') {
            toast.warning(`File '${file.name}' already exists`, { id: `dup-${file.name}` })
          } else {
            toast.error(`Failed to upload '${file.name}': ${result.message}`, { id: `err-${file.name}` })
          }
        } catch (err) {
          console.error(`Upload failed for ${file.name}:`, err)
          toast.error(`Upload failed: ${file.name}`, { id: `err-${file.name}` })
        }
      }

      if (hasSuccessfulUpload) {
        toast.success('Files processed successfully', { id: toastId })
        
        // Refresh document list
        if (onDocumentsUploaded) {
          await onDocumentsUploaded()
        }

        // Clear staging area
        setStagedFiles([])
        setUploadProgresses({})
        setOpen(false)
      } else {
        toast.error('No files were uploaded successfully', { id: toastId })
      }
    } catch (err) {
      console.error('Unexpected error during processing:', err)
      toast.error(`Processing error: ${errorMessage(err)}`, { id: toastId })
    } finally {
      setIsUploading(false)
    }
  }, [stagedFiles, onDocumentsUploaded])

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        if (isUploading) return
        if (!open) {
          setUploadProgresses({})
        }
        setOpen(open)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="default" side="bottom" tooltip="Upload with Temporal Sequencing" size="sm">
          <UploadIcon /> Temporal Upload
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl max-h-[80vh] flex flex-col" onCloseAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Temporal Document Upload</DialogTitle>
          <DialogDescription>
            Sequence your documents from oldest to newest. The order determines versioning (v1, v2, v3...).
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto">
          {/* File Input */}
          <div className="mb-4">
            <input
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx"
              onChange={handleFileSelect}
              disabled={isUploading}
              className="block w-full text-sm text-gray-500
                file:mr-4 file:py-2 file:px-4
                file:rounded file:border-0
                file:text-sm file:font-semibold
                file:bg-primary file:text-primary-foreground
                hover:file:bg-primary/90
                disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Staging Area List */}
          {stagedFiles.length > 0 ? (
            <div className="space-y-2">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-semibold text-sm">Staged Files ({stagedFiles.length})</h3>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setStagedFiles([])}
                  disabled={isUploading}
                >
                  Clear All
                </Button>
              </div>

              {stagedFiles.map((stagedFile, index) => (
                <div
                  key={`${stagedFile.file.name}-${index}`}
                  className="flex items-center gap-2 p-3 border rounded bg-card hover:bg-accent/5 transition-colors"
                >
                  {/* Sequence Badge */}
                  <div className="flex flex-col items-center justify-center min-w-[60px]">
                    <span className="text-xs text-muted-foreground">
                      {index === 0 ? 'Oldest' : index === stagedFiles.length - 1 ? 'Newest' : `Seq`}
                    </span>
                    <span className="font-bold text-lg">v{stagedFile.sequenceIndex}</span>
                  </div>

                  {/* File Info */}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{stagedFile.file.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {(stagedFile.file.size / 1024).toFixed(2)} KB
                    </div>
                    {uploadProgresses[stagedFile.file.name] !== undefined && (
                      <div className="mt-1">
                        <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary transition-all duration-300"
                            style={{ width: `${uploadProgresses[stagedFile.file.name]}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => moveUp(index)}
                      disabled={index === 0 || isUploading}
                      title="Move Up"
                    >
                      <ChevronUp className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => moveDown(index)}
                      disabled={index === stagedFiles.length - 1 || isUploading}
                      title="Move Down"
                    >
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeFile(index)}
                      disabled={isUploading}
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <p>No files staged. Select files above to begin.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={isUploading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleProcessFiles}
            disabled={stagedFiles.length === 0 || isUploading}
          >
            {isUploading ? 'Processing...' : `Process ${stagedFiles.length} File(s)`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
