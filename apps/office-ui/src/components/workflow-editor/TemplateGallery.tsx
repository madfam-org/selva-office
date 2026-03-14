'use client';

import { useState, useEffect, useCallback, type FC } from 'react';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useWorkflowTemplates, type WorkflowTemplate } from '@/hooks/useWorkflowTemplates';
import type { WorkflowDetail } from '@/hooks/useWorkflow';

interface TemplateGalleryProps {
  open: boolean;
  onClose: () => void;
  onCreated: (workflow: WorkflowDetail) => void;
}

const CATEGORIES = ['All', 'Development', 'Creative', 'Data', 'Operations'] as const;
type CategoryFilter = (typeof CATEGORIES)[number];

const CATEGORY_ICONS: Record<string, string> = {
  Development: '\u2699',
  Creative: '\u270E',
  Data: '\u2630',
  Operations: '\u26A1',
  Other: '\u2726',
};

function CategoryBadge({ category }: { category: string }) {
  const colorMap: Record<string, string> = {
    Development: 'bg-cyan-900/60 text-cyan-300 border-cyan-700',
    Creative: 'bg-purple-900/60 text-purple-300 border-purple-700',
    Data: 'bg-amber-900/60 text-amber-300 border-amber-700',
    Operations: 'bg-emerald-900/60 text-emerald-300 border-emerald-700',
  };
  const colors = colorMap[category] ?? 'bg-slate-800 text-slate-300 border-slate-600';
  return (
    <span
      className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[7px] uppercase ${colors}`}
    >
      {CATEGORY_ICONS[category] ?? '\u2726'} {category}
    </span>
  );
}

function TemplateCard({
  template,
  onSelect,
}: {
  template: WorkflowTemplate;
  onSelect: (template: WorkflowTemplate) => void;
}) {
  return (
    <div
      className="retro-panel cursor-pointer p-3 transition-all duration-150 hover:translate-y-[-1px] hover:shadow-[0_0_8px_rgba(99,102,241,0.3)] animate-fade-in-up"
      onClick={() => onSelect(template)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(template);
        }
      }}
      aria-label={`Select template ${template.name}`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="pixel-text text-[9px] text-indigo-400 leading-tight">
          {template.name}
        </h3>
        <CategoryBadge category={template.category} />
      </div>

      <p className="mb-2 font-mono text-[8px] text-slate-300 line-clamp-2 leading-relaxed">
        {template.description}
      </p>

      <div className="flex items-center justify-between">
        <span className="font-mono text-[8px] text-slate-500">
          {template.node_count} {template.node_count === 1 ? 'node' : 'nodes'}
        </span>
      </div>
    </div>
  );
}

function TemplatePreview({
  template,
  onBack,
  onCreateWorkflow,
  creating,
}: {
  template: WorkflowTemplate;
  onBack: () => void;
  onCreateWorkflow: (template: WorkflowTemplate, name?: string) => void;
  creating: boolean;
}) {
  const [customName, setCustomName] = useState('');

  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {/* Back button */}
      <button
        onClick={onBack}
        className="self-start font-mono text-[9px] text-slate-400 transition-colors hover:text-white"
        aria-label="Back to template list"
      >
        &larr; Back to templates
      </button>

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="pixel-text text-[11px] text-indigo-400">{template.name}</h3>
          <div className="mt-1 flex items-center gap-2">
            <CategoryBadge category={template.category} />
            <span className="font-mono text-[8px] text-slate-500">
              {template.node_count} nodes
            </span>
          </div>
        </div>
      </div>

      {/* Description */}
      <div>
        <h4 className="pixel-text mb-1 text-[8px] uppercase text-slate-500">Description</h4>
        <p className="font-mono text-[9px] text-slate-300 leading-relaxed">
          {template.description}
        </p>
      </div>

      {/* Custom name input */}
      <div>
        <h4 className="pixel-text mb-1 text-[8px] uppercase text-slate-500">Workflow Name</h4>
        <input
          type="text"
          value={customName}
          onChange={(e) => setCustomName(e.target.value)}
          placeholder={template.name}
          className="w-full rounded border border-slate-700 bg-slate-800/80 px-2 py-1.5 font-mono text-[9px] text-slate-200 placeholder:text-slate-600 focus:border-indigo-500 focus:outline-none"
          aria-label="Custom workflow name"
        />
      </div>

      {/* Create button */}
      <button
        onClick={() => onCreateWorkflow(template, customName.trim() || undefined)}
        disabled={creating}
        className="self-start rounded bg-indigo-600 px-4 py-2 font-mono text-[9px] text-white transition-colors hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed retro-btn"
        aria-label="Create workflow from template"
      >
        {creating ? 'Creating...' : 'Create Workflow'}
      </button>
    </div>
  );
}

export const TemplateGallery: FC<TemplateGalleryProps> = ({ open, onClose, onCreated }) => {
  const trapRef = useFocusTrap<HTMLDivElement>(open);
  const { templates, status, error, fetchTemplates, createFromTemplate } =
    useWorkflowTemplates();

  const [category, setCategory] = useState<CategoryFilter>('All');
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplate | null>(null);

  // Fetch templates on open
  useEffect(() => {
    if (open) {
      fetchTemplates();
    }
  }, [open, fetchTemplates]);

  // Reset state when closing
  useEffect(() => {
    if (!open) {
      setCategory('All');
      setSelectedTemplate(null);
    }
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        if (selectedTemplate) {
          setSelectedTemplate(null);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose, selectedTemplate]);

  const handleSelectTemplate = useCallback((template: WorkflowTemplate) => {
    setSelectedTemplate(template);
  }, []);

  const handleCreateWorkflow = useCallback(
    async (template: WorkflowTemplate, name?: string) => {
      const result = await createFromTemplate(template.filename, name);
      if (result) {
        onCreated(result);
        onClose();
      }
    },
    [createFromTemplate, onCreated, onClose],
  );

  const filteredTemplates =
    category === 'All'
      ? templates
      : templates.filter((t) => t.category === category);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-modal animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Template Gallery"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-900/95 backdrop-blur-sm" onClick={onClose} />

      {/* Modal container */}
      <div
        ref={trapRef}
        className="absolute inset-4 sm:inset-6 lg:inset-8 retro-panel pixel-border-accent animate-pop-in flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex flex-col gap-3 border-b border-slate-700 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="pixel-text text-[11px] uppercase tracking-wider text-indigo-400">
            Workflow Templates
          </h2>

          <button
            onClick={onClose}
            className="rounded bg-slate-800 px-2 py-1 font-mono text-[9px] text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
            aria-label="Close template gallery"
          >
            [X]
          </button>
        </div>

        {/* Category filter tabs */}
        <div className="flex gap-1 overflow-x-auto border-b border-slate-800 px-3 py-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`whitespace-nowrap px-2 py-1 font-mono text-[8px] uppercase transition-colors ${
                category === cat
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {/* Error state */}
          {error && (
            <div className="mb-3 rounded border border-red-500/50 bg-red-900/20 px-3 py-2 font-mono text-[9px] text-red-400">
              {error}
            </div>
          )}

          {/* Loading state */}
          {status === 'loading' && !selectedTemplate && (
            <div className="flex items-center justify-center py-12">
              <p className="pixel-text animate-pulse text-[10px] text-slate-500">Loading...</p>
            </div>
          )}

          {/* Preview view */}
          {selectedTemplate ? (
            <TemplatePreview
              template={selectedTemplate}
              onBack={() => setSelectedTemplate(null)}
              onCreateWorkflow={handleCreateWorkflow}
              creating={status === 'creating'}
            />
          ) : status !== 'loading' ? (
            <>
              {/* Empty state */}
              {filteredTemplates.length === 0 && (
                <div className="flex flex-col items-center justify-center py-12">
                  <p className="pixel-text text-[10px] text-slate-500">No templates found</p>
                  <p className="mt-2 font-mono text-[8px] text-slate-600">
                    {category !== 'All'
                      ? 'Try selecting a different category'
                      : 'No workflow templates are available'}
                  </p>
                </div>
              )}

              {/* Card grid */}
              {filteredTemplates.length > 0 && (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {filteredTemplates.map((template, idx) => (
                    <div key={template.filename} style={{ animationDelay: `${idx * 50}ms` }}>
                      <TemplateCard template={template} onSelect={handleSelectTemplate} />
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
