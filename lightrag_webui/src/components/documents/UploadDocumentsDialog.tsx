import { useState, useCallback } from 'react'
import { FileRejection } from 'react-dropzone'
import Button from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import FileUploader from '@/components/ui/FileUploader'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/utils'
import { ingestBatch, IngestManifest } from '@/api/lightrag'

import { UploadIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface UploadDocumentsDialogProps {
  onDocumentsUploaded?: () => Promise<void>
}

export default function UploadDocumentsDialog({ onDocumentsUploaded }: UploadDocumentsDialogProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progresses, setProgresses] = useState<Record<string, number>>({})
  const [fileErrors, setFileErrors] = useState<Record<string, string>>({})
  const [files, setFiles] = useState<File[]>([])
  // Optional overrides for batch manifest
  const [docTypeOverride, setDocTypeOverride] = useState<string>('')
  const [effDateOverride, setEffDateOverride] = useState<string>('')
  // Per-file overrides keyed by a stable file key
  const [perFileOverrides, setPerFileOverrides] = useState<Record<string, { docType?: string; effectiveDate?: string }>>({})

  const getFileKey = useCallback((f: File) => `${f.name}|${f.size}|${(f as any).lastModified ?? ''}`,[ ])

  const handleRejectedFiles = useCallback(
    (rejectedFiles: FileRejection[]) => {
      // Process rejected files and add them to fileErrors
      rejectedFiles.forEach(({ file, errors }) => {
        // Get the first error message
        let errorMsg = errors[0]?.message || t('documentPanel.uploadDocuments.fileUploader.fileRejected', { name: file.name })

        // Simplify error message for unsupported file types
        if (errorMsg.includes('file-invalid-type')) {
          errorMsg = t('documentPanel.uploadDocuments.fileUploader.unsupportedType')
        }

        // Set progress to 100% to display error message
        setProgresses((pre) => ({
          ...pre,
          [file.name]: 100
        }))

        // Add error message to fileErrors
        setFileErrors(prev => ({
          ...prev,
          [file.name]: errorMsg
        }))
      })
    },
    [setProgresses, setFileErrors, t]
  )

  const handleDocumentsUpload = useCallback(
    async (filesToUpload: File[]) => {
      setIsUploading(true)
      let hasSuccessfulUpload = false

      // Only clear errors for files that are being uploaded, keep errors for rejected files
      setFileErrors(prev => {
        const newErrors = { ...prev };
        filesToUpload.forEach(file => {
          delete newErrors[file.name];
        });
        return newErrors;
      });

      // Show uploading toast
      const toastId = toast.loading(t('documentPanel.uploadDocuments.batch.uploading'))

      try {
        // Track errors locally to ensure we have the final state
        const uploadErrors: Record<string, string> = {}

        // Preserve current visual order from the uploader for sequence
        const sortedFiles = [...filesToUpload]

        // Initialize per-file progress to 0
        setProgresses((pre) => {
          const next = { ...pre }
          for (const f of sortedFiles) {
            next[f.name] = 0
          }
          return next
        })

        // Build manifest for batch ingestion (minimal: id, name, type)
        const manifest: IngestManifest = {
          items: sortedFiles.map((f, idx) => {
            const key = getFileKey(f)
            const per = perFileOverrides[key] || {}
            return {
              id: `${idx + 1}`,
              name: f.name,
              type: 'file' as const,
              sequence: idx + 1,
              ...(docTypeOverride ? { docType: docTypeOverride } : {}),
              ...(effDateOverride ? { effectiveDate: effDateOverride } : {}),
              ...(per.docType ? { docType: per.docType } : {}),
              ...(per.effectiveDate ? { effectiveDate: per.effectiveDate } : {}),
            }
          }),
        }

        try {
          const result = await ingestBatch(sortedFiles, manifest, (percentCompleted: number) => {
            // Update all file progresses uniformly since this is a single batch request
            setProgresses((pre) => {
              const next = { ...pre }
              for (const f of sortedFiles) {
                next[f.name] = percentCompleted
              }
              return next
            })
          })

          if (result.status === 'failure') {
            // Mark errors for all files on failure
            const message = result.message || t('documentPanel.uploadDocuments.batch.error')
            for (const f of sortedFiles) {
              uploadErrors[f.name] = message
            }
            setFileErrors(prev => {
              const next = { ...prev }
              for (const f of sortedFiles) {
                next[f.name] = message
              }
              return next
            })
          } else {
            // success or partial_success: mark completed
            hasSuccessfulUpload = true
            setProgresses((pre) => {
              const next = { ...pre }
              for (const f of sortedFiles) {
                next[f.name] = 100
              }
              return next
            })
          }
        } catch (err) {
          // Handle HTTP errors (e.g., auth, network)
          let errorMsg = errorMessage(err)
          // Set each file to 100% to display error message
          setProgresses((pre) => {
            const next = { ...pre }
            for (const f of sortedFiles) {
              next[f.name] = 100
            }
            return next
          })
          // Record error message for each file
          setFileErrors(prev => {
            const next = { ...prev }
            for (const f of sortedFiles) {
              next[f.name] = errorMsg
              uploadErrors[f.name] = errorMsg
            }
            return next
          })
        }

        // Check if any files failed to upload using our local tracking
        const hasErrors = Object.keys(uploadErrors).length > 0

        // Update toast status
        if (hasErrors) {
          toast.error(t('documentPanel.uploadDocuments.batch.error'), { id: toastId })
        } else {
          toast.success(t('documentPanel.uploadDocuments.batch.success'), { id: toastId })
        }

        // Only update if at least one file was uploaded successfully
        if (hasSuccessfulUpload) {
          // Refresh document list
          if (onDocumentsUploaded) {
            onDocumentsUploaded().catch(err => {
              console.error('Error refreshing documents:', err)
            })
          }
        }
      } catch (err) {
        console.error('Unexpected error during upload:', err)
        toast.error(t('documentPanel.uploadDocuments.generalError', { error: errorMessage(err) }), { id: toastId })
      } finally {
        setIsUploading(false)
      }
    },
    [setIsUploading, setProgresses, setFileErrors, t, onDocumentsUploaded]
  )

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        if (isUploading) {
          return
        }
        if (!open) {
          setProgresses({})
          setFileErrors({})
        }
        setOpen(open)
      }}
    >
      <DialogTrigger asChild>
        <Button variant="default" side="bottom" tooltip={t('documentPanel.uploadDocuments.tooltip')} size="sm">
          <UploadIcon /> {t('documentPanel.uploadDocuments.button')}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl" onCloseAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('documentPanel.uploadDocuments.title')}</DialogTitle>
          <DialogDescription>
            {t('documentPanel.uploadDocuments.description')}
          </DialogDescription>
        </DialogHeader>
        {/* Optional temporal overrides for batch ingestion */}
        <div className="grid grid-cols-1 gap-3 mb-3">
          <div className="flex items-center gap-2">
            <label htmlFor="docTypeOverride" className="text-sm whitespace-nowrap">Document Type (optional)</label>
            <input
              id="docTypeOverride"
              type="text"
              value={docTypeOverride}
              onChange={(e) => setDocTypeOverride(e.target.value)}
              className="flex-1 h-9 rounded-md border px-2 text-sm"
              placeholder="e.g., amendment, addendum, rate-sheet"
            />
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="effDateOverride" className="text-sm whitespace-nowrap">Effective Date (optional)</label>
            <input
              id="effDateOverride"
              type="date"
              value={effDateOverride}
              onChange={(e) => setEffDateOverride(e.target.value)}
              className="flex-1 h-9 rounded-md border px-2 text-sm"
            />
          </div>
        </div>
        <FileUploader
          value={files}
          onValueChange={setFiles}
          maxFileCount={Infinity}
          maxSize={200 * 1024 * 1024}
          description={t('documentPanel.uploadDocuments.fileTypes')}
          onReject={handleRejectedFiles}
          progresses={progresses}
          fileErrors={fileErrors}
          disabled={isUploading}
          renderFileExtras={(file) => {
            const key = getFileKey(file)
            const cur = perFileOverrides[key] || {}
            return (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div className="flex items-center gap-2">
                  <label className="text-xs whitespace-nowrap">Doc Type (optional)</label>
                  <input
                    type="text"
                    value={cur.docType || ''}
                    onChange={(e) => setPerFileOverrides(prev => ({ ...prev, [key]: { ...prev[key], docType: e.target.value } }))}
                    className="flex-1 h-8 rounded-md border px-2 text-xs"
                    placeholder="e.g., amendment"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs whitespace-nowrap">Effective Date (optional)</label>
                  <input
                    type="date"
                    value={cur.effectiveDate || ''}
                    onChange={(e) => setPerFileOverrides(prev => ({ ...prev, [key]: { ...prev[key], effectiveDate: e.target.value } }))}
                    className="flex-1 h-8 rounded-md border px-2 text-xs"
                  />
                </div>
              </div>
            )
          }}
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="default"
            size="sm"
            disabled={isUploading || files.length === 0}
            onClick={() => handleDocumentsUpload(files)}
          >
            <UploadIcon /> {t('documentPanel.uploadDocuments.batch.startUpload')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
