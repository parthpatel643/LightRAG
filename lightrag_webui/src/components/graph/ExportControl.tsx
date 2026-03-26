import { useSigma } from '@react-sigma/core'
import { Download, Image, FileCode } from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { useWorkspaceStore } from '@/stores/workspace'

export default function ExportControl() {
  const sigma = useSigma()
  const [isExporting, setIsExporting] = useState(false)
  const currentWorkspace = useWorkspaceStore.use.currentWorkspace()

  const getFilename = (extension: string) => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)
    const workspace = currentWorkspace || 'default'
    return `lightrag-graph-${workspace}-${timestamp}.${extension}`
  }

  const exportToPNG = async () => {
    if (isExporting) return
    setIsExporting(true)

    try {
      // Get the container and find the main canvas element
      const container = sigma.getContainer()
      const canvases = container.querySelectorAll('canvas')
      
      // Find the main WebGL canvas (usually the largest or first one)
      let canvas: HTMLCanvasElement | null = null
      if (canvases.length > 0) {
        // Try to find canvas with specific class or just use the first one
        canvas = canvases[0] as HTMLCanvasElement
      }
      
      if (!canvas) {
        throw new Error('Canvas not found')
      }
      
      // Create a new canvas with white background
      const exportCanvas = document.createElement('canvas')
      const dpr = window.devicePixelRatio || 1
      
      // Use the display size, not the internal size
      const displayWidth = canvas.clientWidth || canvas.width / dpr
      const displayHeight = canvas.clientHeight || canvas.height / dpr
      
      exportCanvas.width = displayWidth * dpr
      exportCanvas.height = displayHeight * dpr
      exportCanvas.style.width = `${displayWidth}px`
      exportCanvas.style.height = `${displayHeight}px`
      
      const ctx = exportCanvas.getContext('2d')
      
      if (!ctx) {
        throw new Error('Could not get canvas context')
      }

      // Scale for device pixel ratio
      ctx.scale(dpr, dpr)

      // Fill with white background
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, displayWidth, displayHeight)
      
      // Draw the graph on top
      ctx.drawImage(canvas, 0, 0, displayWidth, displayHeight)

      // Convert to blob and download
      exportCanvas.toBlob((blob) => {
        if (!blob) {
          toast.error('Failed to export graph')
          return
        }

        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = getFilename('png')
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)

        toast.success('Graph exported as PNG')
      }, 'image/png')
    } catch (error) {
      console.error('Export error:', error)
      toast.error('Failed to export graph')
    } finally {
      setIsExporting(false)
    }
  }

  const exportToSVG = async () => {
    if (isExporting) return
    setIsExporting(true)

    try {
      const graph = sigma.getGraph()
      const camera = sigma.getCamera()
      
      // Get graph bounds
      const nodes = graph.nodes()
      if (nodes.length === 0) {
        toast.error('No nodes to export')
        setIsExporting(false)
        return
      }

      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      
      nodes.forEach(node => {
        const attrs = graph.getNodeAttributes(node)
        const x = attrs.x
        const y = attrs.y
        const size = attrs.size || 5
        
        minX = Math.min(minX, x - size)
        minY = Math.min(minY, y - size)
        maxX = Math.max(maxX, x + size)
        maxY = Math.max(maxY, y + size)
      })

      const padding = 50
      const width = maxX - minX + padding * 2
      const height = maxY - minY + padding * 2

      // Create SVG
      let svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minX - padding} ${minY - padding} ${width} ${height}">
  <rect width="100%" height="100%" fill="white"/>
  <g id="edges">\n`

      // Add edges
      graph.forEachEdge((edge, attrs, source, target) => {
        const sourceAttrs = graph.getNodeAttributes(source)
        const targetAttrs = graph.getNodeAttributes(target)
        const color = attrs.color || '#999999'
        const size = attrs.size || 1

        svg += `    <line x1="${sourceAttrs.x}" y1="${sourceAttrs.y}" x2="${targetAttrs.x}" y2="${targetAttrs.y}" stroke="${color}" stroke-width="${size}" opacity="0.5"/>\n`
      })

      svg += `  </g>
  <g id="nodes">\n`

      // Add nodes
      graph.forEachNode((node, attrs) => {
        const x = attrs.x
        const y = attrs.y
        const size = attrs.size || 5
        const color = attrs.color || '#666666'
        const label = attrs.label || node

        svg += `    <circle cx="${x}" cy="${y}" r="${size}" fill="${color}"/>\n`
        svg += `    <text x="${x}" y="${y + size + 12}" text-anchor="middle" font-size="10" fill="#333333">${label}</text>\n`
      })

      svg += `  </g>
</svg>`

      // Download SVG
      const blob = new Blob([svg], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = getFilename('svg')
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)

      toast.success('Graph exported as SVG')
    } catch (error) {
      console.error('Export error:', error)
      toast.error('Failed to export graph')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="flex flex-col gap-1 p-1">
      <button
        onClick={exportToPNG}
        disabled={isExporting}
        className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title="Export as PNG"
      >
        <Image className="h-4 w-4" />
        <span>PNG</span>
      </button>
      <button
        onClick={exportToSVG}
        disabled={isExporting}
        className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title="Export as SVG"
      >
        <FileCode className="h-4 w-4" />
        <span>SVG</span>
      </button>
    </div>
  )
}

// Made with Bob
