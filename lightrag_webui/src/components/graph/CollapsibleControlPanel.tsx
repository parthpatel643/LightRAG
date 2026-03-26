import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import LayoutsControl from './LayoutsControl'
import ZoomControl from './ZoomControl'
import FullScreenControl from './FullScreenControl'
import ExportControl from './ExportControl'
import LegendButton from './LegendButton'
import Settings from './Settings'

interface ControlSection {
  id: string
  title: string
  component: React.ReactNode
  defaultOpen?: boolean
}

export default function CollapsibleControlPanel() {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['view']) // View section open by default
  )

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(sectionId)) {
        newSet.delete(sectionId)
      } else {
        newSet.add(sectionId)
      }
      return newSet
    })
  }

  const sections: ControlSection[] = [
    {
      id: 'view',
      title: 'View',
      component: (
        <>
          <ZoomControl />
          <FullScreenControl />
        </>
      ),
      defaultOpen: true
    },
    {
      id: 'layout',
      title: 'Layout',
      component: <LayoutsControl />
    },
    {
      id: 'export',
      title: 'Export',
      component: <ExportControl />
    },
    {
      id: 'display',
      title: 'Display',
      component: (
        <>
          <LegendButton />
          <Settings />
        </>
      )
    }
  ]

  return (
    <div className="bg-white/95 dark:bg-gray-900/95 absolute bottom-2 left-2 rounded-xl border-2 border-gray-200 dark:border-gray-700 backdrop-blur-lg overflow-hidden shadow-lg">
      {sections.map((section, index) => {
        const isExpanded = expandedSections.has(section.id)
        const isLast = index === sections.length - 1

        return (
          <div key={section.id} className={!isLast ? 'border-b border-gray-200 dark:border-gray-700' : ''}>
            {/* Section Header */}
            <button
              onClick={() => toggleSection(section.id)}
              className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-900 dark:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <span>{section.title}</span>
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>

            {/* Section Content */}
            {isExpanded && (
              <div className="border-t border-gray-200 dark:border-gray-700">
                {section.component}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// Made with Bob
