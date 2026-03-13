import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, Reorder, AnimatePresence } from 'framer-motion'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '@/components/ui/Dialog'
import { 
  Upload, 
  GripVertical, 
  X, 
  Calendar, 
  FileText, 
  CheckCircle2,
  AlertCircle,
  Sparkles
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { batchUploadSequenced } from '@/api/lightrag'
import { cn } from '@/lib/utils'

interface DocumentWithMetadata {
  file: File
  effectiveDate?: string
  sequenceIndex?: number
  id: string
}

interface DocumentSequencerProps {
  onUploadComplete?: () => void
  className?: string
}

export default function DocumentSequencer({ onUploadComplete, className }: DocumentSequencerProps) {
  const { t } = useTranslation()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [documents, setDocuments] = useState<DocumentWithMetadata[]>([])
  const [currentStep, setCurrentStep] = useState<'upload' | 'sequence' | 'metadata' | 'confirm'>('upload')
  const [isUploading, setIsUploading] = useState(false)

  // File upload handler
  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newDocs: DocumentWithMetadata[] = acceptedFiles.map((file, index) => ({
      file,
      id: `${file.name}-${Date.now()}-${index}`,
      sequenceIndex: documents.length + index
    }))
    setDocuments(prev => [...prev, ...newDocs])
    toast.success(t('sequencer.filesAdded', `Added ${acceptedFiles.length} file(s)`))
  }, [documents.length, t])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/markdown': ['.md']
    }
  })

  // Reorder handler for Framer Motion
  const handleReorder = (newOrder: DocumentWithMetadata[]) => {
    const reindexed = newOrder.map((doc, idx) => ({
      ...doc,
      sequenceIndex: idx
    }))
    setDocuments(reindexed)
  }

  // Remove document
  const removeDocument = (id: string) => {
    setDocuments(prev => {
      const filtered = prev.filter(doc => doc.id !== id)
      return filtered.map((doc, idx) => ({ ...doc, sequenceIndex: idx }))
    })
  }

  // Update effective date
  const updateEffectiveDate = (id: string, date: string) => {
    setDocuments(prev =>
      prev.map(doc => (doc.id === id ? { ...doc, effectiveDate: date } : doc))
    )
  }

  // Handle upload
  const handleUpload = async () => {
    if (documents.length === 0) {
      toast.error(t('sequencer.noDocuments', 'Please add documents first'))
      return
    }

    const missingDates = documents.filter(doc => !doc.effectiveDate)
    if (missingDates.length > 0) {
      toast.error(
        t('sequencer.missingDates', 'Please set effective dates for all documents')
      )
      return
    }

    setIsUploading(true)

    try {
      const order = documents.map(doc => doc.file.name)
      const metadata = documents.reduce((acc, doc) => {
        acc[doc.file.name] = {
          effective_date: doc.effectiveDate,
          sequence_index: doc.sequenceIndex
        }
        return acc
      }, {} as Record<string, any>)

      await batchUploadSequenced(
        documents.map(doc => doc.file),
        order,
        metadata
      )

      toast.success(
        t('sequencer.uploadSuccess', 'Documents uploaded and sequenced successfully')
      )

      setDocuments([])
      setCurrentStep('upload')
      setIsDialogOpen(false)
      
      if (onUploadComplete) {
        onUploadComplete()
      }
    } catch (error) {
      console.error('Upload failed:', error)
      toast.error(t('sequencer.uploadError', 'Failed to upload documents'))
    } finally {
      setIsUploading(false)
    }
  }

  // Reset dialog
  const handleClose = () => {
    if (!isUploading) {
      setDocuments([])
      setCurrentStep('upload')
      setIsDialogOpen(false)
    }
  }

  // Step navigation
  const canProceedToSequence = documents.length > 0
  const canProceedToMetadata = documents.length > 0
  const canProceedToConfirm = documents.every(doc => doc.effectiveDate)

  const steps = [
    { key: 'upload', label: 'Upload', icon: Upload },
    { key: 'sequence', label: 'Sequence', icon: GripVertical },
    { key: 'metadata', label: 'Dates', icon: Calendar },
    { key: 'confirm', label: 'Confirm', icon: CheckCircle2 }
  ] as const

  const currentStepIndex = steps.findIndex(s => s.key === currentStep)

  return (
    <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
      <DialogTrigger asChild>
        <Button variant="default" className={cn("group", className)}>
          <Upload className="h-4 w-4 mr-2" />
          {t('documentPanel.uploadDocuments.button', 'Upload')}
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[800px] max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-xl">
            {t('sequencer.title', 'Temporal Document Sequencing')}
          </DialogTitle>
          <DialogDescription>
            {t('sequencer.description', 
              'Upload, sequence, and timestamp your documents for powerful temporal queries.'
            )}
          </DialogDescription>
        </DialogHeader>

        {/* Enhanced Step indicator */}
        <div className="flex items-center justify-between px-2 py-4">
          {steps.map((step, index) => {
            const Icon = step.icon
            const isActive = currentStep === step.key
            const isCompleted = index < currentStepIndex
            
            return (
              <div key={step.key} className="flex items-center flex-1">
                <motion.div
                  className="flex flex-col items-center flex-1"
                  initial={false}
                  animate={{
                    scale: isActive ? 1.05 : 1
                  }}
                >
                  <motion.div
                    className={cn(
                      'flex items-center justify-center w-10 h-10 rounded-full text-sm font-medium transition-all',
                      isActive
                        ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/50'
                        : isCompleted
                        ? 'bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500'
                    )}
                    whileHover={{ scale: 1.1 }}
                  >
                    <Icon className="h-5 w-5" />
                  </motion.div>
                  <span className={cn(
                    "text-xs mt-1 font-medium",
                    isActive ? "text-emerald-600 dark:text-emerald-400" : "text-gray-500 dark:text-gray-400"
                  )}>
                    {step.label}
                  </span>
                </motion.div>
                {index < steps.length - 1 && (
                  <div className="flex-1 h-0.5 mx-2 bg-gray-200 dark:bg-gray-700 relative overflow-hidden">
                    <motion.div
                      className="absolute inset-0 bg-emerald-500 dark:bg-emerald-400"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: isCompleted ? 1 : 0 }}
                      transition={{ duration: 0.3 }}
                      style={{ transformOrigin: 'left' }}
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Content area with animation */}
        <div className="flex-1 overflow-y-auto px-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {/* Step 1: Upload */}
              {currentStep === 'upload' && (
                <div className="space-y-4">
                  <motion.div
                    {...getRootProps()}
                    className={cn(
                      'border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all',
                      isDragActive
                        ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950 scale-105'
                        : 'border-gray-300 dark:border-gray-600 hover:border-emerald-400 dark:hover:border-emerald-500 hover:bg-gray-50 dark:hover:bg-gray-800'
                    )}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                  >
                    <input {...getInputProps()} />
                    <motion.div
                      animate={{ y: isDragActive ? -5 : 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <Upload className={cn(
                        "h-16 w-16 mx-auto mb-4 transition-colors",
                        isDragActive ? "text-emerald-500 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"
                      )} />
                    </motion.div>
                    <p className="text-base font-medium text-gray-700 dark:text-gray-200 mb-2">
                      {isDragActive
                        ? t('sequencer.dropFiles', 'Drop files here...')
                        : t('sequencer.dragDrop', 'Drag & drop files here, or click to browse')}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {t('sequencer.supportedFormats', 'Supported: TXT, PDF, DOC, DOCX, MD')}
                    </p>
                  </motion.div>

                  {documents.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <label className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                          {t('sequencer.uploadedFiles', 'Uploaded Files')} ({documents.length})
                        </label>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDocuments([])}
                          className="text-xs"
                        >
                          Clear All
                        </Button>
                      </div>
                      <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
                        <AnimatePresence>
                          {documents.map(doc => (
                            <motion.div
                              key={doc.id}
                              initial={{ opacity: 0, scale: 0.9 }}
                              animate={{ opacity: 1, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.9, x: -100 }}
                              className="flex items-center justify-between p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:shadow-md transition-shadow"
                            >
                              <div className="flex items-center gap-3 flex-1 min-w-0">
                                <FileText className="h-5 w-5 text-emerald-500 dark:text-emerald-400 flex-shrink-0" />
                                <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{doc.file.name}</span>
                                <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                                  {(doc.file.size / 1024).toFixed(1)} KB
                                </span>
                              </div>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => removeDocument(doc.id)}
                                className="hover:bg-red-50 dark:hover:bg-red-950 hover:text-red-600 dark:hover:text-red-400"
                              >
                                <X className="h-4 w-4" />
                              </Button>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                      </div>
                    </motion.div>
                  )}
                </div>
              )}

              {/* Step 2: Sequence with Framer Motion Reorder */}
              {currentStep === 'sequence' && (
                <div className="space-y-4">
                  <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-1">
                          {t('sequencer.arrangeOrder', 'Arrange Document Order')}
                        </p>
                        <p className="text-xs text-blue-700 dark:text-blue-300">
                          {t('sequencer.arrangeHelp', 'Drag and drop documents to reorder them chronologically. The first document should be the earliest.')}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <Reorder.Group
                    axis="y"
                    values={documents}
                    onReorder={handleReorder}
                    className="space-y-2 max-h-[400px] overflow-y-auto pr-2"
                  >
                    <AnimatePresence>
                      {documents.map((doc, index) => (
                        <Reorder.Item
                          key={doc.id}
                          value={doc}
                          className="list-none"
                          whileDrag={{
                            scale: 1.05,
                            boxShadow: "0 10px 30px rgba(0,0,0,0.15)",
                            cursor: "grabbing"
                          }}
                        >
                          <motion.div
                            layout
                            className="flex items-center gap-3 p-4 bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 rounded-xl cursor-grab active:cursor-grabbing hover:border-emerald-300 dark:hover:border-emerald-500 transition-colors group"
                          >
                            <GripVertical className="h-6 w-6 text-gray-400 dark:text-gray-500 group-hover:text-emerald-500 dark:group-hover:text-emerald-400 transition-colors flex-shrink-0" />
                            <motion.div
                              className="flex items-center justify-center w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300 font-bold text-sm flex-shrink-0"
                              layout
                            >
                              {index + 1}
                            </motion.div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{doc.file.name}</p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {(doc.file.size / 1024).toFixed(1)} KB
                              </p>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                              <span className="hidden sm:inline">Drag to reorder</span>
                            </div>
                          </motion.div>
                        </Reorder.Item>
                      ))}
                    </AnimatePresence>
                  </Reorder.Group>
                </div>
              )}

              {/* Step 3: Metadata */}
              {currentStep === 'metadata' && (
                <div className="space-y-4">
                  <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                    <div className="flex items-start gap-3">
                      <Calendar className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-sm font-medium text-amber-900 dark:text-amber-100 mb-1">
                          {t('sequencer.setDates', 'Set Effective Dates')}
                        </p>
                        <p className="text-xs text-amber-700 dark:text-amber-300">
                          {t('sequencer.datesHelp', 'Assign effective dates to enable temporal queries. These dates determine when each document version becomes active.')}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                    <AnimatePresence>
                      {documents.map((doc, index) => (
                        <motion.div
                          key={doc.id}
                          layout
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: index * 0.05 }}
                          className="flex items-center gap-3 p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl hover:shadow-md transition-shadow"
                        >
                          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-bold text-sm flex-shrink-0">
                            {index + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{doc.file.name}</p>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <Calendar className={cn(
                              "h-4 w-4 transition-colors",
                              doc.effectiveDate ? "text-emerald-500 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"
                            )} />
                            <Input
                              type="date"
                              value={doc.effectiveDate || ''}
                              onChange={(e) => updateEffectiveDate(doc.id, e.target.value)}
                              className={cn(
                                "w-40 transition-all",
                                doc.effectiveDate ? "border-emerald-300 dark:border-emerald-600" : ""
                              )}
                              placeholder="Select date"
                            />
                          </div>
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  </div>
                </div>
              )}

              {/* Step 4: Confirm */}
              {currentStep === 'confirm' && (
                <div className="space-y-4">
                  <motion.div
                    initial={{ scale: 0.9, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="flex items-center gap-3 p-4 bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-xl"
                  >
                    <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-semibold text-emerald-900 dark:text-emerald-100">
                        {t('sequencer.reviewUpload', 'Ready to Upload')}
                      </p>
                      <p className="text-xs text-emerald-700 dark:text-emerald-300">
                        {t('sequencer.confirmMessage',
                          `${documents.length} document(s) sequenced and ready for temporal queries`
                        )}
                      </p>
                    </div>
                  </motion.div>
                  
                  <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
                    {documents.map((doc, index) => (
                      <motion.div
                        key={doc.id}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3 flex-1 min-w-0">
                            <div className="flex items-center justify-center w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300 font-bold text-sm flex-shrink-0">
                              {index + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate mb-2">{doc.file.name}</p>
                              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400">
                                <span className="flex items-center gap-1">
                                  <Calendar className="h-3 w-3" />
                                  {doc.effectiveDate}
                                </span>
                                <span>
                                  {(doc.file.size / 1024).toFixed(1)} KB
                                </span>
                              </div>
                            </div>
                          </div>
                          <CheckCircle2 className="h-5 w-5 text-emerald-500 dark:text-emerald-400 flex-shrink-0" />
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        <DialogFooter className="flex justify-between border-t pt-4">
          <Button variant="outline" onClick={handleClose} disabled={isUploading}>
            {t('common.cancel', 'Cancel')}
          </Button>
          
          <div className="flex gap-2">
            {currentStep !== 'upload' && (
              <Button
                variant="outline"
                onClick={() => {
                  const stepKeys = ['upload', 'sequence', 'metadata', 'confirm'] as const
                  const currentIndex = stepKeys.indexOf(currentStep)
                  if (currentIndex > 0) {
                    setCurrentStep(stepKeys[currentIndex - 1])
                  }
                }}
                disabled={isUploading}
              >
                {t('common.back', 'Back')}
              </Button>
            )}
            
            {currentStep === 'upload' && (
              <Button
                onClick={() => setCurrentStep('sequence')}
                disabled={!canProceedToSequence}
              >
                {t('common.next', 'Next: Sequence')}
              </Button>
            )}
            
            {currentStep === 'sequence' && (
              <Button
                onClick={() => setCurrentStep('metadata')}
                disabled={!canProceedToMetadata}
              >
                {t('common.next', 'Next: Set Dates')}
              </Button>
            )}
            
            {currentStep === 'metadata' && (
              <Button
                onClick={() => setCurrentStep('confirm')}
                disabled={!canProceedToConfirm}
                className={cn(
                  !canProceedToConfirm && "opacity-50"
                )}
              >
                {t('common.next', 'Next: Review')}
              </Button>
            )}
            
            {currentStep === 'confirm' && (
              <Button 
                onClick={handleUpload} 
                disabled={isUploading}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                {isUploading
                  ? t('sequencer.uploading', 'Uploading...')
                  : t('sequencer.upload', 'Upload Documents')}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Made with Bob
