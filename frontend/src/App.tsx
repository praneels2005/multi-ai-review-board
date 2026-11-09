import React, { useState, useEffect } from 'react';
import { startReview, observeReview, rememberRun, rememberedRun } from './reviewExecution';
import {
  Brain,
  Shield,
  Zap,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Clock,
  Sparkles,
  ArrowRight,
  RefreshCw,
  Plus,
  Trash2,
  AlertOctagon,
  Layers,
  Activity,
  History,
  X,
  Play,
  HelpCircle,
  Sliders,
  DollarSign,
  Cpu,
  Radio,
  Check,
  GitBranch
} from 'lucide-react';

/* ================= TYPES ================= */

interface EvidenceItem {
  id: string;
  source: string;
  summary: string;
  data_type: 'metric' | 'customer_interview' | 'market_report' | 'benchmark' | 'pilot' | 'anecdote' | 'other';
}

interface StartupIdeaInput {
  title: string;
  idea: string;
  target_customer: string;
  problem: string;
  proposed_solution: string;
  evidence: EvidenceItem[];
}

interface SpecialistAgentConfig {
  id: string;
  role: string;
  expertise: string;
  mandate: string;
  rationale: string;
  provider: 'mock' | 'openai' | 'gemini';
  model: string;
  simulate_failure?: 'timeout' | 'provider_error' | 'malformed_output' | null;
}

interface ValidationExperiment {
  hypothesis: string;
  test_design: string;
  success_metric: string;
}

interface SpecialistFeedback {
  specialist_id: string;
  role: string;
  provider: string;
  model: string;
  is_simulated: boolean;
  status: 'success' | 'failed' | 'timed_out';
  error_message?: string | null;
  strengths: string[];
  risks: string[];
  missing_assumptions: string[];
  questions: string[];
  validation_experiment?: ValidationExperiment | null;
  evidence_citations: string[];
  invalid_citations: string[];
  assumptions_and_unknowns: string[];
  latency_ms: number;
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  cost_estimate_usd: number;
}

interface ChallengeResponseItem {
  challenger_id: string;
  challenger_role: string;
  challenger_provider?: string;
  target_specialist_id: string;
  target_role: string;
  target_provider?: string;
  target_model?: string;
  challenge_point: string;
  response: string;
  reasoning_adjustment: string;
  is_simulated: boolean;
}

interface EvidenceSufficiencyAssessment {
  status: 'sufficient' | 'thin' | 'insufficient';
  analysis: string;
}

interface CoordinatorCombinedReview {
  summary: string;
  priorities: string[];
  disagreements: string[];
  next_experiments: ValidationExperiment[];
  evidence_sufficiency: EvidenceSufficiencyAssessment;
  failure_impact_analysis?: string | null;
  disclaimer: string;
  is_fallback?: boolean;
  status?: 'success' | 'failed' | 'timed_out';
  latency_ms: number;
  token_usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  cost_estimate_usd: number;
}

interface BudgetConfig {
  call_cap: number;
  token_cap: number;
  timeout_seconds: number;
  max_retries: number;
}

interface ReviewBoardSession {
  session_id: string;
  created_at: string;
  idea: StartupIdeaInput;
  panel: SpecialistAgentConfig[];
  budget_config: BudgetConfig;
  specialist_reviews: SpecialistFeedback[];
  challenge_round: ChallengeResponseItem[];
  combined_review?: CoordinatorCombinedReview | null;
  status: 'draft' | 'panel_generated' | 'in_progress' | 'completed' | 'partial_failure' | 'failed' | 'budget_stopped';
  rerun_of_session_id?: string | null;
  version?: number;
  rerun_history?: string[];
  execution_summary: {
    total_latency_ms: number;
    total_tokens: number;
    total_cost_usd: number;
    reported_tokens?: number;
    estimated_tokens?: number;
    simulated_tokens?: number;
    calls_made: number;
    budget_stopped: boolean;
    failures_encountered: number;
  };
}

interface SessionSummary {
  session_id: string;
  created_at: string;
  title: string;
  status: string;
  version?: number;
  rerun_of_session_id?: string | null;
  specialist_count: number;
  failures_encountered: number;
  total_cost_usd: number;
  evidence_status: string;
}

const API_BASE = 'http://localhost:8000';

export default function App() {
  // State
  const [presets, setPresets] = useState<Record<string, { name: string; description: string; idea: StartupIdeaInput }>>({});
  const [isLoadingPresets, setIsLoadingPresets] = useState(true);
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>('devtool_ebpf');
  const [panelGenProvider, setPanelGenProvider] = useState<'mock' | 'openai' | 'gemini'>('mock');
  
  const [idea, setIdea] = useState<StartupIdeaInput>({
    title: '',
    idea: '',
    target_customer: '',
    problem: '',
    proposed_solution: '',
    evidence: []
  });

  const [panel, setPanel] = useState<SpecialistAgentConfig[]>([]);
  const [budget, setBudget] = useState<BudgetConfig>({
    call_cap: 20,
    token_cap: 50000,
    timeout_seconds: 12.0,
    max_retries: 1
  });

  const [currentSession, setCurrentSession] = useState<ReviewBoardSession | null>(null);
  const [isGeneratingPanel, setIsGeneratingPanel] = useState(false);
  const [isRunningReview, setIsRunningReview] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Live Real-Time Agent Progress Tracking
  const [currentPhase, setCurrentPhase] = useState<'idle' | 'specialists' | 'debate' | 'coordinator'>('idle');
  const [activeSpecialistId, setActiveSpecialistId] = useState<string | null>(null);
  const [liveAgentStatus, setLiveAgentStatus] = useState<Record<string, { status: string; latency_ms?: number }>>({});

  // History Drawer State
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [savedSessions, setSavedSessions] = useState<SessionSummary[]>([]);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [activeTab, setActiveTab] = useState<'board' | 'combined' | 'specialists' | 'debate'>('board');

  // Load presets on mount
  useEffect(() => {
    // Capture before recovery can finish and clear the remembered identifier.
    fetchPresets(rememberedRun() === null);
    fetchSavedSessions();
  }, []);

  const fetchPresets = async (applyDefault: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/review-board/presets`);
      if (res.ok) {
        const data = await res.json();
        setPresets(data);
        if (applyDefault && data.devtool_ebpf) {
          applyPreset('devtool_ebpf', data.devtool_ebpf.idea);
        }
      }
    } catch (err) {
      console.error('Failed to load presets:', err);
    } finally {
      setIsLoadingPresets(false);
    }
  };

  const fetchSavedSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/review-board/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSavedSessions(data);
      }
    } catch (err) {
      console.error('Failed to load saved sessions:', err);
    }
  };

  const applyPreset = (key: string, presetIdea: StartupIdeaInput) => {
    setSelectedPresetKey(key);
    setIdea(JSON.parse(JSON.stringify(presetIdea)));
    setPanel([]);
    setCurrentSession(null);
    setErrorMessage(null);
    setLiveAgentStatus({});
    setCurrentPhase('idle');
  };

  const startCustomIdea = () => {
    if (isLoadingPresets || isGeneratingPanel || isRunningReview) return;
    applyPreset('', {
      title: '', idea: '', target_customer: '', problem: '', proposed_solution: '', evidence: []
    });
    setActiveSpecialistId(null);
    setActiveTab('board');
  };

  // Generate Panel
  const handleGeneratePanel = async () => {
    if (!idea.title || !idea.idea) {
      setErrorMessage('Please provide an idea title and description.');
      return;
    }
    setIsGeneratingPanel(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/review-board/generate-panel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea,
          provider: panelGenProvider
        })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Panel generation failed');
      }
      const data: SpecialistAgentConfig[] = await res.json();
      setPanel(data);
      setLiveAgentStatus({});
      setActiveTab('board');
    } catch (err: any) {
      setErrorMessage(err.message);
    } finally {
      setIsGeneratingPanel(false);
    }
  };

  // Run Review Board with Real-Time Event Streaming
  const handleRunReview = async () => {
    if (panel.length < 3 || panel.length > 5) {
      setErrorMessage(`Panel must contain between 3 and 5 specialists (currently ${panel.length}).`);
      return;
    }

    const uniqueIds = new Set(panel.map(s => s.id));
    if (uniqueIds.size !== panel.length) {
      setErrorMessage('Specialist IDs must be unique across the panel.');
      return;
    }

    setIsRunningReview(true);
    setErrorMessage(null);
    setCurrentPhase('specialists');
    setLiveAgentStatus({});

    try {
      await startReview({ session_id: crypto.randomUUID(), idea, panel, budget_config: budget }, handleStreamEvent);
      fetchSavedSessions();
    } catch (err: any) {
      setErrorMessage(err.message);
    } finally {
      setIsRunningReview(false);
      setCurrentPhase('idle');
      setActiveSpecialistId(null);
    }
  };

  const handleStreamEvent = (event: any) => {
    if (event.type === 'session_snapshot') {
      setCurrentSession(event.session);
      setCurrentPhase(event.session.run_metadata?.phase === 'pending' ? 'specialists' : event.session.run_metadata?.phase || 'specialists');
      setActiveSpecialistId(event.session.run_metadata?.active_specialist_id || null);
      const statuses = Object.fromEntries(event.session.specialist_reviews.map((review: any) =>
        [review.specialist_id, { status: review.status, latency_ms: review.latency_ms }]));
      const activeId = event.session.run_metadata?.active_specialist_id;
      if (activeId) statuses[activeId] = { status: 'running' };
      setLiveAgentStatus(statuses);
    } else if (event.type === 'phase_started') {
      setCurrentPhase(event.phase);
    } else if (event.type === 'specialist_started') {
      setActiveSpecialistId(event.specialist_id);
      setLiveAgentStatus(prev => ({
        ...prev,
        [event.specialist_id]: { status: 'running' }
      }));
    } else if (event.type === 'specialist_completed') {
      setActiveSpecialistId(null);
      setLiveAgentStatus(prev => ({
        ...prev,
        [event.specialist_id]: { status: event.status, latency_ms: event.latency_ms }
      }));
    } else if (event.type === 'session_final') {
      if (event.session.run_metadata?.interrupted) setErrorMessage(event.session.run_metadata.interruption_reason);
      setCurrentSession(event.session);
      setActiveTab('combined');
    }
  };

  useEffect(() => {
    const id = rememberedRun();
    if (!id) return;
    setIsRunningReview(true);
    observeReview(id, null, event => {
      handleStreamEvent(event);
      setIdea(event.session.idea);
      setPanel(event.session.panel);
      setBudget(event.session.budget_config);
    })
      .then(() => { fetchSavedSessions(); })
      .catch((error: Error) => setErrorMessage(error.message))
      .finally(() => { setIsRunningReview(false); setCurrentPhase('idle'); setActiveSpecialistId(null); });
  }, []);

  // Reopen a saved session
  const handleReopenSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/review-board/sessions/${sessionId}`);
      if (!res.ok) throw new Error('Session not found');
      const data: ReviewBoardSession = await res.json();
      setCurrentSession(data);
      setIdea(data.idea);
      setPanel(data.panel);
      setBudget(data.budget_config);
      setIsHistoryOpen(false);
      setActiveTab('combined');
      if (data.status === 'in_progress') {
        rememberRun(sessionId);
        setIsRunningReview(true);
        try { await observeReview(sessionId, data, handleStreamEvent); }
        finally { setIsRunningReview(false); setCurrentPhase('idle'); setActiveSpecialistId(null); }
      }
    } catch (err: any) {
      setErrorMessage(err.message);
    }
  };

  // Rerun current session with history preservation
  const handleRerunSession = async () => {
    if (!currentSession) return;
    const childId = crypto.randomUUID();
    rememberRun(childId);
    setIsRunningReview(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/review-board/sessions/${currentSession.session_id}/rerun`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': childId },
        body: JSON.stringify(budget)
      });
      if (!res.ok) throw new Error('Rerun failed');
      const data: ReviewBoardSession = await res.json();
      rememberRun(null);
      setCurrentSession(data);
      fetchSavedSessions();
    } catch (err: any) {
      try { await observeReview(childId, null, handleStreamEvent); }
      catch { setErrorMessage(err.message); }
    } finally {
      setIsRunningReview(false);
    }
  };

  // Evidence Management
  const addEvidenceItem = () => {
    const nextId = `E${idea.evidence.length + 1}`;
    setIdea({
      ...idea,
      evidence: [
        ...idea.evidence,
        { id: nextId, source: 'Source description or URL', summary: 'Empirical finding or metric summary', data_type: 'metric' }
      ]
    });
  };

  const removeEvidenceItem = (index: number) => {
    const updated = idea.evidence.filter((_, i) => i !== index);
    setIdea({ ...idea, evidence: updated });
  };

  // Panel Specialist Updates
  const updateSpecialist = (index: number, field: keyof SpecialistAgentConfig, value: any) => {
    const updated = [...panel];
    updated[index] = { ...updated[index], [field]: value };
    setPanel(updated);
  };

  const removeSpecialist = (index: number) => {
    setPanel(panel.filter((_, i) => i !== index));
  };

  const addCustomSpecialist = () => {
    if (panel.length >= 5) {
      setErrorMessage('Panel maximum is 5 specialists.');
      return;
    }
    const newSpec: SpecialistAgentConfig = {
      id: `spec_${panel.length + 1}`,
      role: 'Custom Domain Specialist',
      expertise: 'Describe unique domain expertise...',
      mandate: 'Describe what questions this specialist must answer...',
      rationale: 'Why this review perspective is necessary...',
      provider: 'mock',
      model: 'mock-deterministic',
      simulate_failure: null
    };
    setPanel([...panel, newSpec]);
  };

  return (
    <div className="min-h-screen bg-[#080811] text-slate-100 font-sans pb-20">
      {/* ── HEADER ── */}
      <header className="border-b border-slate-800/80 bg-[#0d0d1a]/80 backdrop-blur sticky top-0 z-40 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Brain className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-white">Multiple AI Review Board</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">
                  v1.1.0
                </span>
              </div>
              <p className="text-xs text-slate-400">Multi-agent startup evaluation with cross-provider debates & evidence grounding</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowConfigModal(true)}
              className="flex items-center gap-2 text-xs bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/80 text-slate-300 px-3 py-2 rounded-lg transition"
            >
              <Sliders className="w-3.5 h-3.5 text-indigo-400" />
              <span>Budget & Caps</span>
            </button>

            <button
              onClick={() => setIsHistoryOpen(true)}
              className="flex items-center gap-2 text-xs bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/80 text-slate-300 px-3 py-2 rounded-lg transition relative"
            >
              <History className="w-3.5 h-3.5 text-violet-400" />
              <span>Saved Reviews ({savedSessions.length})</span>
            </button>
          </div>
        </div>
      </header>

      {/* ── ERROR NOTIFICATION ── */}
      {errorMessage && (
        <div className="max-w-7xl mx-auto mt-4 px-6">
          <div className="bg-red-950/40 border border-red-500/40 text-red-200 px-4 py-3 rounded-xl flex items-center justify-between text-sm shadow-lg">
            <div className="flex items-center gap-2">
              <AlertOctagon className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button onClick={() => setErrorMessage(null)} className="text-red-400 hover:text-red-200">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* ── PRESETS BAR ── */}
      <div className="max-w-7xl mx-auto px-6 pt-6">
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Walkthrough Presets:</span>
            <p className="text-xs text-slate-400">Select contrasting ideas to demonstrate domain-tailored panels, evidence tests, and debate rounds</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={startCustomIdea}
              disabled={isLoadingPresets || isGeneratingPanel || isRunningReview}
              className="text-xs px-3.5 py-2 rounded-xl border border-indigo-500/50 text-indigo-200 bg-indigo-600/20 hover:bg-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed transition font-semibold"
            >
              Start with your own idea
            </button>
            {Object.entries(presets).map(([key, item]) => (
              <button
                key={key}
                onClick={() => applyPreset(key, item.idea)}
                className={`text-xs px-3.5 py-2 rounded-xl border transition font-medium text-left ${
                  selectedPresetKey === key
                    ? 'bg-indigo-600/20 border-indigo-500/50 text-indigo-200 shadow-sm'
                    : 'bg-slate-800/40 border-slate-700/60 text-slate-400 hover:bg-slate-800/70 hover:text-slate-200'
                }`}
              >
                <div className="font-semibold">{item.name.split(':')[1]?.trim() || item.name}</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  {key === 'thin_evidence_neuro' ? '⚠️ Thin Evidence Test' : 'Contrasting Domain'}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── LIVE PIPELINE STEPPER (visible when running) ── */}
      {isRunningReview && (
        <div className="max-w-7xl mx-auto px-6 pt-4">
          <div className="bg-indigo-950/30 border border-indigo-500/30 rounded-2xl p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center animate-spin">
                <RefreshCw className="w-4 h-4 text-indigo-300" />
              </div>
              <div>
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  <span>Executing Review Board</span>
                  <span className="bg-indigo-500/20 text-indigo-300 font-mono text-[10px] px-2 py-0.5 rounded-full uppercase">
                    Phase: {currentPhase}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400">
                  {currentPhase === 'specialists' && activeSpecialistId && (
                    <span>Evaluating specialist <strong className="text-indigo-300">{activeSpecialistId}</strong> independently...</span>
                  )}
                  {currentPhase === 'debate' && <span>Conducting cross-agent debate round between specialists...</span>}
                  {currentPhase === 'coordinator' && <span>Synthesizing decision support report and assessing evidence sufficiency...</span>}
                </div>
              </div>
            </div>
            <div className="text-xs font-mono text-indigo-400 animate-pulse">
              ● Live Multi-Agent Streaming
            </div>
          </div>
        </div>
      )}

      {/* ── MAIN WORKSPACE ── */}
      <main className="max-w-7xl mx-auto px-6 pt-6 grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* LEFT COLUMN: Idea & Panel Input (5 cols) */}
        <section className="lg:col-span-5 space-y-6">
          {/* Card: Startup Idea Input */}
          <div className="bg-[#0f0f1d] border border-slate-800/90 rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <h2 className="font-semibold text-sm text-slate-100">1. Startup Idea & Evidence Context</h2>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">{selectedPresetKey ? `ID: ${selectedPresetKey}` : 'Custom idea'}</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Startup Title</label>
                <input
                  type="text"
                  value={idea.title}
                  onChange={(e) => setIdea({ ...idea, title: e.target.value })}
                  placeholder="e.g., DevPulse Continuous Profiler"
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Target Customer</label>
                <input
                  type="text"
                  value={idea.target_customer}
                  onChange={(e) => setIdea({ ...idea, target_customer: e.target.value })}
                  placeholder="e.g., Platform Engineers & DevOps Leads"
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Problem</label>
                <textarea
                  rows={2}
                  value={idea.problem}
                  onChange={(e) => setIdea({ ...idea, problem: e.target.value })}
                  placeholder="What specific problem is being solved?"
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition resize-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Proposed Solution</label>
                <textarea
                  rows={2}
                  value={idea.proposed_solution}
                  onChange={(e) => setIdea({ ...idea, proposed_solution: e.target.value })}
                  placeholder="How does your product solve this?"
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition resize-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Full Concept Description</label>
                <textarea
                  rows={3}
                  value={idea.idea}
                  onChange={(e) => setIdea({ ...idea, idea: e.target.value })}
                  placeholder="Detailed architecture or business model description..."
                  className="w-full bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-indigo-500 transition resize-none"
                />
              </div>
            </div>

            {/* Evidence Items Section */}
            <div className="border-t border-slate-800/80 pt-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-semibold text-slate-300">Supplied Evidence Items</h3>
                  <p className="text-[11px] text-slate-400">Specialists and coordinator verify these specific IDs (E1, E2)</p>
                </div>
                <button
                  type="button"
                  onClick={addEvidenceItem}
                  className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 px-2 py-1 rounded-md border border-indigo-500/20 transition"
                >
                  <Plus className="w-3 h-3" /> Add Evidence
                </button>
              </div>

              {idea.evidence.length === 0 ? (
                <div className="bg-amber-950/20 border border-amber-500/20 rounded-xl p-3 text-xs text-amber-300/80 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>No empirical evidence supplied. Review board will evaluate as unbacked claims (insufficient evidence).</span>
                </div>
              ) : (
                <div className="space-y-2">
                  {idea.evidence.map((item, idx) => (
                    <div key={item.id} className="bg-slate-900/90 border border-slate-800 rounded-xl p-3 text-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-500/30">
                            {item.id}
                          </span>
                          <select
                            value={item.data_type}
                            onChange={(e) => {
                              const ev = [...idea.evidence];
                              ev[idx].data_type = e.target.value as any;
                              setIdea({ ...idea, evidence: ev });
                            }}
                            className="text-[10px] bg-slate-800 text-slate-300 rounded px-1.5 py-0.5 border border-slate-700"
                          >
                            <option value="benchmark">Benchmark</option>
                            <option value="customer_interview">Customer Interview</option>
                            <option value="metric">Quantitative Metric</option>
                            <option value="pilot">Pilot Cohort</option>
                            <option value="anecdote">Anecdote / Testimonial</option>
                            <option value="market_report">Market Report</option>
                          </select>
                        </div>
                        <button onClick={() => removeEvidenceItem(idx)} className="text-slate-400 hover:text-red-400 transition">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <input
                        type="text"
                        value={item.source}
                        onChange={(e) => {
                          const ev = [...idea.evidence];
                          ev[idx].source = e.target.value;
                          setIdea({ ...idea, evidence: ev });
                        }}
                        placeholder="Source origin (e.g. 50-node benchmark)"
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-300 focus:outline-none"
                      />
                      <textarea
                        rows={2}
                        value={item.summary}
                        onChange={(e) => {
                          const ev = [...idea.evidence];
                          ev[idx].summary = e.target.value;
                          setIdea({ ...idea, evidence: ev });
                        }}
                        placeholder="Key metric or empirical takeaway"
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-300 focus:outline-none resize-none"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Panel Generation Provider Options */}
            <div className="border-t border-slate-800/80 pt-3 flex items-center justify-between">
              <span className="text-[11px] text-slate-400">Generator Model:</span>
              <select
                value={panelGenProvider}
                onChange={(e) => setPanelGenProvider(e.target.value as any)}
                className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs text-slate-300"
              >
                <option value="mock">Deterministic Mock</option>
                <option value="openai">OpenAI (gpt-4o-mini)</option>
                <option value="gemini">Google Gemini (1.5-flash)</option>
              </select>
            </div>

            <button
              onClick={handleGeneratePanel}
              disabled={isGeneratingPanel}
              className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 disabled:opacity-50 transition"
            >
              {isGeneratingPanel ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Generating Tailored Panel...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  Generate 3–5 Specialist Panel
                </>
              )}
            </button>
          </div>

          {/* Panel Inspector & Customizer */}
          {panel.length > 0 && (
            <div className="bg-[#0f0f1d] border border-slate-800/90 rounded-2xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-violet-400" />
                  <h2 className="font-semibold text-sm text-slate-100">2. Review Board Panel ({panel.length}/5)</h2>
                </div>
                {panel.length < 5 && (
                  <button
                    onClick={addCustomSpecialist}
                    className="flex items-center gap-1 text-[11px] text-violet-400 hover:text-violet-300 bg-violet-500/10 px-2 py-1 rounded-md border border-violet-500/20 transition"
                  >
                    <Plus className="w-3 h-3" /> Add Specialist
                  </button>
                )}
              </div>

              <p className="text-xs text-slate-400">
                Inspect mandates, adjust roles, or assign providers/models per specialist before running.
              </p>

              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                {panel.map((spec, idx) => {
                  const live = liveAgentStatus[spec.id];
                  return (
                    <div
                      key={spec.id}
                      className={`bg-slate-900/90 border rounded-xl p-3 text-xs space-y-2 transition ${
                        live?.status === 'running'
                          ? 'border-indigo-500 ring-1 ring-indigo-500/50 shadow-lg shadow-indigo-500/20'
                          : live?.status === 'success'
                          ? 'border-emerald-500/40'
                          : live?.status === 'failed' || live?.status === 'timed_out'
                          ? 'border-red-500/40'
                          : 'border-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-indigo-400 font-bold">{spec.id}</span>
                          {live?.status === 'running' && (
                            <span className="flex items-center gap-1 text-[10px] text-indigo-300 bg-indigo-500/20 px-1.5 py-0.2 rounded font-mono animate-pulse">
                              <RefreshCw className="w-2.5 h-2.5 animate-spin" /> Running
                            </span>
                          )}
                          {live?.status === 'success' && (
                            <span className="text-[10px] text-emerald-300 bg-emerald-500/20 px-1.5 py-0.2 rounded font-mono">
                              ✓ Done ({live.latency_ms?.toFixed(0)}ms)
                            </span>
                          )}
                        </div>
                        {panel.length > 3 && (
                          <button onClick={() => removeSpecialist(idx)} className="text-slate-400 hover:text-red-400">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>

                      <input
                        type="text"
                        value={spec.role}
                        onChange={(e) => updateSpecialist(idx, 'role', e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 font-semibold text-slate-200 text-xs"
                        placeholder="Specialist Role Title"
                      />

                      <div>
                        <span className="text-[10px] text-slate-400 font-medium">Review Mandate:</span>
                        <textarea
                          rows={2}
                          value={spec.mandate}
                          onChange={(e) => updateSpecialist(idx, 'mandate', e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-300 resize-none mt-0.5"
                        />
                      </div>

                      {/* Provider & Model Selector */}
                      <div className="grid grid-cols-2 gap-2 pt-1">
                        <div>
                          <label className="text-[10px] text-slate-400">AI Provider</label>
                          <select
                            value={spec.provider}
                            onChange={(e) => {
                              const p = e.target.value as SpecialistAgentConfig['provider'];
                              let defaultModel = 'mock-deterministic';
                              if (p === 'openai') defaultModel = 'gpt-4o-mini';
                              if (p === 'gemini') defaultModel = 'gemini-1.5-flash';
                              setPanel(previous => previous.map((specialist, index) =>
                                index === idx
                                  ? { ...specialist, provider: p, model: defaultModel }
                                  : specialist
                              ));
                            }}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-300 mt-0.5"
                          >
                            <option value="mock">Deterministic Mock</option>
                            <option value="openai">OpenAI (AsyncOpenAI)</option>
                            <option value="gemini">Google Gemini (GenAI SDK)</option>
                          </select>
                        </div>

                        <div>
                          <label className="text-[10px] text-slate-400">Model</label>
                          <input
                            type="text"
                            value={spec.model}
                            onChange={(e) => updateSpecialist(idx, 'model', e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-2 py-1 text-[11px] text-slate-300 mt-0.5"
                          />
                        </div>
                      </div>

                      {/* Failure Simulation Dropdown */}
                      <div className="bg-slate-950/60 p-2 rounded border border-slate-800/60 mt-1">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-slate-400">Simulate Failure (Demo Resilience):</span>
                          <select
                            value={spec.simulate_failure || ''}
                            onChange={(e) => updateSpecialist(idx, 'simulate_failure', e.target.value || null)}
                            className="bg-slate-900 border border-slate-700/80 rounded px-1.5 py-0.5 text-[10px] text-amber-300"
                          >
                            <option value="">None (Normal)</option>
                            <option value="timeout">Simulate Timeout</option>
                            <option value="provider_error">Simulate Connection Error</option>
                            <option value="malformed_output">Simulate Malformed JSON</option>
                          </select>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <button
                onClick={handleRunReview}
                disabled={isRunningReview || panel.length < 3 || panel.length > 5}
                className="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/20 disabled:opacity-50 transition"
              >
                {isRunningReview ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Executing Live Review Board...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-white" />
                    Run Review Board ({panel.length} Specialists)
                  </>
                )}
              </button>
            </div>
          )}
        </section>

        {/* RIGHT COLUMN: Output Dashboard & Tabs (7 cols) */}
        <section className="lg:col-span-7 space-y-6">
          {/* Navigation Tabs */}
          <div className="flex items-center gap-2 border-b border-slate-800/80 pb-3 overflow-x-auto">
            <button
              onClick={() => setActiveTab('combined')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                activeTab === 'combined'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Brain className="w-3.5 h-3.5" />
              Coordinator Synthesis
            </button>

            <button
              onClick={() => setActiveTab('specialists')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                activeTab === 'specialists'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Specialist Feedback ({currentSession?.specialist_reviews?.length || panel.length})
            </button>

            <button
              onClick={() => setActiveTab('debate')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                activeTab === 'debate'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              Cross-Agent Debate ({currentSession?.challenge_round?.length || 0})
            </button>
          </div>

          {/* Execution Metric Strip (if session active) */}
          {currentSession && (
            <div className="bg-slate-900/60 border border-slate-800/90 rounded-xl p-3 flex flex-wrap items-center justify-between text-xs gap-3">
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded font-mono font-bold uppercase text-[10px] ${
                  currentSession.status === 'completed' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                  currentSession.status === 'partial_failure' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                  currentSession.status === 'budget_stopped' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' :
                  'bg-red-500/20 text-red-300 border border-red-500/30'
                }`}>
                  Status: {currentSession.status}
                </span>
                {currentSession.version && currentSession.version > 1 && (
                  <span className="flex items-center gap-1 font-mono text-[10px] text-violet-400 bg-violet-500/10 px-1.5 py-0.5 rounded border border-violet-500/20">
                    <GitBranch className="w-3 h-3" /> v{currentSession.version}
                  </span>
                )}
                <span className="text-slate-400">Calls: {currentSession.execution_summary.calls_made}</span>
              </div>

              <div className="flex items-center gap-4 text-slate-400 font-mono text-[11px]">
                <div className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{currentSession.execution_summary.total_latency_ms.toFixed(0)} ms</span>
                </div>
                <div className="flex items-center gap-1">
                  <Cpu className="w-3.5 h-3.5 text-violet-400" />
                  <span>
                    {currentSession.execution_summary.total_tokens.toLocaleString()} tokens
                    {currentSession.execution_summary.reported_tokens !== undefined ? (
                      <> ({currentSession.execution_summary.reported_tokens.toLocaleString()} reported / {currentSession.execution_summary.estimated_tokens?.toLocaleString() ?? '0'} estimated / {currentSession.execution_summary.simulated_tokens?.toLocaleString() ?? '0'} simulated)</>
                    ) : ' (usage source unavailable)'}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Est. cost: ${currentSession.execution_summary.total_cost_usd.toFixed(5)}</span>
                </div>
              </div>

              <button
                onClick={handleRerunSession}
                disabled={isRunningReview}
                className="flex items-center gap-1 text-[11px] text-indigo-300 hover:text-white bg-indigo-500/20 hover:bg-indigo-500/30 px-2.5 py-1 rounded-lg border border-indigo-500/30 transition"
              >
                <RefreshCw className="w-3 h-3" /> Rerun Review (Saves v{ (currentSession.version || 1) + 1 })
              </button>
            </div>
          )}

          {/* TAB 1: COORDINATOR COMBINED REVIEW */}
          {activeTab === 'combined' && (
            <div className="space-y-6">
              {!currentSession?.combined_review ? (
                <div className="bg-[#0f0f1d] border border-slate-800 rounded-2xl p-10 text-center space-y-3">
                  <Brain className="w-10 h-10 text-slate-400 mx-auto" />
                  <h3 className="text-base font-semibold text-slate-300">No Review Run Yet</h3>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    Generate the specialist panel on the left, adjust parameters, and click &quot;Run Review Board&quot; to synthesize multi-agent findings.
                  </p>
                </div>
              ) : (
                <>
                  {/* Coordinator Fallback Alert Banner (if coordinator failed) */}
                  {currentSession.combined_review.is_fallback && (
                    <div className="bg-red-950/40 border border-red-500/50 rounded-2xl p-4 text-xs text-red-200 flex items-start gap-3 shadow-xl">
                      <AlertOctagon className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                      <div>
                        <strong className="text-red-300 font-bold block text-sm">Coordinator Synthesis Failed (Fallback Guidance Only)</strong>
                        <p className="opacity-90 mt-1">
                          The coordinator model encountered an upstream timeout or failure ({currentSession.combined_review.status}).
                          The assessment below is fallback advisory text; review the individual specialist feedback cards for verified domain opinions.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Coordinator Executive Summary */}
                  <div className="bg-[#0f0f1d] border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-indigo-400" />
                        <h2 className="font-bold text-base text-white">Coordinator Combined Review</h2>
                      </div>
                      <span className="text-[10px] font-mono bg-indigo-500/10 text-indigo-400 px-2 py-0.5 rounded border border-indigo-500/20">
                        Independent Coordinator · Simulated
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed bg-slate-900/60 p-4 rounded-xl border border-slate-800">
                      {currentSession.combined_review.summary}
                    </p>

                    {/* Evidence Sufficiency Assessment Card */}
                    <div className={`p-4 rounded-xl border ${
                      currentSession.combined_review.evidence_sufficiency.status === 'sufficient'
                        ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                        : currentSession.combined_review.evidence_sufficiency.status === 'thin'
                        ? 'bg-amber-950/20 border-amber-500/30 text-amber-200'
                        : 'bg-red-950/20 border-red-500/30 text-red-200'
                    }`}>
                      <div className="flex items-center gap-2 mb-1.5">
                        <Shield className="w-4 h-4 shrink-0" />
                        <span className="font-bold text-xs uppercase tracking-wide">
                          Evidence Grounding: {currentSession.combined_review.evidence_sufficiency.status}
                        </span>
                      </div>
                      <details className="text-xs opacity-90 leading-relaxed">
                        <summary className="cursor-pointer">Evidence analysis</summary>
                        <p className="mt-2">{currentSession.combined_review.evidence_sufficiency.analysis}</p>
                      </details>
                    </div>

                    {/* Failure Impact Analysis Card (if an agent failed) */}
                    {currentSession.combined_review.failure_impact_analysis && (
                      <div className="bg-red-950/30 border border-red-500/40 rounded-xl p-4 text-xs text-red-200 space-y-1">
                        <div className="flex items-center gap-2 font-bold text-red-300">
                          <AlertOctagon className="w-4 h-4" />
                          <span>Specialist Failure Impact Analysis</span>
                        </div>
                        <p className="leading-relaxed opacity-90">
                          {currentSession.combined_review.failure_impact_analysis}
                        </p>
                      </div>
                    )}

                    {/* Next Ranked Experiments */}
                    <div className="space-y-2 pt-2">
                      <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                        <Zap className="w-4 h-4 text-emerald-400" /> Recommended Validation Experiments
                      </h4>
                      <div className="space-y-2">
                        {currentSession.combined_review.next_experiments.slice(0, 3).map((exp, i) => (
                          <details key={`${currentSession.session_id}-${i}`} className="bg-slate-900/80 border border-slate-800/90 rounded-xl p-3 text-xs space-y-1.5">
                            <summary className="cursor-pointer">
                              <span className="font-mono text-[10px] font-bold bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30">
                                EXP #{i + 1}
                              </span>
                              <span className="font-semibold text-slate-200 ml-2">{exp.hypothesis}</span>
                            </summary>
                            <p className="text-slate-400 text-[11px]"><strong className="text-slate-300">Test Design:</strong> {exp.test_design}</p>
                            <p className="text-emerald-400/90 text-[11px]"><strong className="text-emerald-300">Success Metric:</strong> {exp.success_metric}</p>
                          </details>
                        ))}
                        {currentSession.combined_review.next_experiments.length > 3 && (
                          <details className="text-xs text-slate-300">
                            <summary className="cursor-pointer font-semibold text-indigo-300">More recommended experiments</summary>
                        {currentSession.combined_review.next_experiments.slice(3).map((exp, i) => (
                          <details key={`${currentSession.session_id}-${i + 3}`} className="bg-slate-900/80 border border-slate-800/90 rounded-xl p-3 text-xs space-y-1.5">
                            <summary className="cursor-pointer">
                              <span className="font-mono text-[10px] font-bold bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30">
                                EXP #{i + 4}
                              </span>
                              <span className="font-semibold text-slate-200 ml-2">{exp.hypothesis}</span>
                            </summary>
                            <p className="text-slate-400 text-[11px]"><strong className="text-slate-300">Test Design:</strong> {exp.test_design}</p>
                            <p className="text-emerald-400/90 text-[11px]"><strong className="text-emerald-300">Success Metric:</strong> {exp.success_metric}</p>
                          </details>
                        ))}
                          </details>
                        )}
                      </div>
                    </div>

                    <details className="text-xs text-slate-300">
                      <summary className="cursor-pointer font-semibold text-indigo-300">Strategic priorities and detailed findings</summary>
                      {/* Priorities and Disagreements Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        <div className="bg-slate-900/80 border border-slate-800/90 rounded-xl p-4 space-y-2">
                          <h4 className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4" /> Top Strategic Priorities
                          </h4>
                          <ul className="space-y-1.5 text-xs text-slate-300">
                            {currentSession.combined_review.priorities.map((p, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <span className="text-indigo-400 font-mono font-bold">{i + 1}.</span>
                                <span>{p}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <div className="bg-slate-900/80 border border-slate-800/90 rounded-xl p-4 space-y-2">
                          <h4 className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
                            <AlertTriangle className="w-4 h-4" /> Key Disagreements & Tensions
                          </h4>
                          <ul className="space-y-1.5 text-xs text-slate-300">
                            {currentSession.combined_review.disagreements.map((d, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <span className="text-amber-400 font-mono font-bold">•</span>
                                <span>{d}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>

                    </details>

                    {/* Decision Support Advisory Disclaimer */}
                    <div className="border-t border-slate-800/80 pt-4 flex items-center gap-2 text-[11px] text-slate-400 italic">
                      <HelpCircle className="w-4 h-4 text-slate-400 shrink-0" />
                      <span>{currentSession.combined_review.disclaimer}</span>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* TAB 2: SPECIALIST FEEDBACK CARDS */}
          {activeTab === 'specialists' && (
            <div className="space-y-4">
              {!currentSession?.specialist_reviews?.length ? (
                <div className="bg-[#0f0f1d] border border-slate-800 rounded-2xl p-10 text-center space-y-3">
                  <Layers className="w-10 h-10 text-slate-400 mx-auto" />
                  <h3 className="text-base font-semibold text-slate-300">No Specialist Output Available</h3>
                  <p className="text-xs text-slate-400">Run the review board to inspect each specialist&apos;s independent review.</p>
                </div>
              ) : (
                currentSession.specialist_reviews.map((spec) => (
                  <div key={spec.specialist_id} className="bg-[#0f0f1d] border border-slate-800/90 rounded-2xl p-6 shadow-xl space-y-4">
                    {/* Header with Role & Provider details */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-indigo-400">{spec.specialist_id}</span>
                          <h3 className="font-bold text-sm text-slate-100">{spec.role}</h3>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">
                            {spec.provider} / {spec.model}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                            spec.is_simulated ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          }`}>
                            {spec.is_simulated ? 'Simulated' : 'Live API Call'}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
                        <span>{spec.latency_ms.toFixed(0)} ms</span>
                        <span>{spec.token_usage?.total_tokens || 0} tokens ({spec.is_simulated ? 'simulated' : 'reported/estimated'})</span>
                        <span>Est. cost: ${(spec.cost_estimate_usd || 0).toFixed(5)}</span>
                      </div>
                    </div>

                    {/* Failure Alert Banner (if failed) */}
                    {spec.status !== 'success' && (
                      <div className="bg-red-950/40 border border-red-500/40 p-3 rounded-xl text-xs text-red-200 flex items-center gap-2">
                        <AlertOctagon className="w-4 h-4 text-red-400 shrink-0" />
                        <div>
                          <strong>Specialist Execution Failed ({spec.status}):</strong> {spec.error_message}
                          <div className="text-[11px] text-red-300 mt-0.5">Failure was isolated; remaining specialists continued without crashing.</div>
                        </div>
                      </div>
                    )}

                    {spec.status === 'success' && (
                      <div className="space-y-4 text-xs">
                        {/* Evidence Citations & Invalid Flagging */}
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-slate-400 font-medium">Evidence Cited:</span>
                          {spec.evidence_citations.length === 0 && spec.invalid_citations.length === 0 && (
                            <span className="text-slate-400 italic">None cited</span>
                          )}
                          {spec.evidence_citations.map((cite) => (
                            <span key={cite} className="bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono px-2 py-0.5 rounded-full font-bold">
                              ✓ {cite} (Valid)
                            </span>
                          ))}
                          {spec.invalid_citations.map((cite) => (
                            <span key={cite} className="bg-red-500/20 text-red-300 border border-red-500/30 font-mono px-2 py-0.5 rounded-full font-bold">
                              ⚠️ {cite} (Invalid / Unsupplied ID)
                            </span>
                          ))}
                        </div>

                        {/* Strengths & Risks */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5">
                            <span className="font-bold text-emerald-400 flex items-center gap-1">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Strengths
                            </span>
                            <ul className="space-y-1 text-slate-300">
                              {spec.strengths.slice(0, 1).map((s, i) => (
                                <li key={i} className="flex items-start gap-1.5">
                                  <span className="text-emerald-500">•</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>

                          <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5">
                            <span className="font-bold text-amber-400 flex items-center gap-1">
                              <AlertTriangle className="w-3.5 h-3.5" /> Critical Risks
                            </span>
                            <ul className="space-y-1 text-slate-300">
                              {spec.risks.slice(0, 1).map((r, i) => (
                                <li key={i} className="flex items-start gap-1.5">
                                  <span className="text-amber-500">•</span>
                                  <span>{r}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>

                        {/* Proposed Experiment */}
                        {spec.validation_experiment && (
                          <div className="bg-slate-900/90 border border-slate-800 p-3 rounded-xl space-y-1">
                            <div className="font-bold text-slate-200 flex items-center gap-1.5">
                              <Zap className="w-3.5 h-3.5 text-emerald-400" />
                              <span>Proposed Validation Experiment</span>
                            </div>
                            <p className="text-slate-300"><strong>Hypothesis:</strong> {spec.validation_experiment.hypothesis}</p>
                            <details>
                              <summary className="cursor-pointer text-indigo-300">Experiment design and success metric</summary>
                              <p className="text-slate-400"><strong>Test Design:</strong> {spec.validation_experiment.test_design}</p>
                              <p className="text-emerald-400"><strong>Success Metric:</strong> {spec.validation_experiment.success_metric}</p>
                            </details>
                          </div>
                        )}

                        <details className="space-y-3">
                          <summary className="cursor-pointer font-semibold text-indigo-300">Additional strengths, risks, assumptions and questions</summary>
                          {spec.strengths.length > 1 && (
                            <div className="space-y-1 text-slate-300">
                              <h4 className="font-bold text-emerald-400">Additional strengths</h4>
                              <ul className="list-disc pl-4 space-y-1">{spec.strengths.slice(1).map((text, i) => <li key={i}>{text}</li>)}</ul>
                            </div>
                          )}
                          {spec.risks.length > 1 && (
                            <div className="space-y-1 text-slate-300">
                              <h4 className="font-bold text-amber-400">Additional risks</h4>
                              <ul className="list-disc pl-4 space-y-1">{spec.risks.slice(1).map((text, i) => <li key={i}>{text}</li>)}</ul>
                            </div>
                          )}
                          {/* Missing Assumptions & Questions */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5">
                              <span className="font-bold text-violet-400">Missing Assumptions</span>
                              <ul className="space-y-1 text-slate-300">
                                {spec.missing_assumptions.map((a, i) => (
                                  <li key={i} className="flex items-start gap-1.5">
                                    <span className="text-violet-400">•</span>
                                    <span>{a}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>

                            <div className="bg-slate-900/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5">
                              <span className="font-bold text-indigo-400">Probing Questions</span>
                              <ul className="space-y-1 text-slate-300">
                                {spec.questions.map((q, i) => (
                                  <li key={i} className="flex items-start gap-1.5">
                                    <span className="text-indigo-400">?</span>
                                    <span>{q}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>

                          {/* Labeled Assumptions / Unknowns */}
                          {spec.assumptions_and_unknowns.length > 0 && (
                            <div className="text-[11px] text-slate-400 space-y-1 border-t border-slate-800/60 pt-2">
                              <span className="font-semibold text-slate-300">Explicitly Labeled Assumptions & Unknowns:</span>
                              <div className="flex flex-wrap gap-1.5">
                                {spec.assumptions_and_unknowns.map((item, i) => (
                                  <span key={i} className="bg-slate-800/80 px-2 py-0.5 rounded text-slate-300">
                                    {item}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </details>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {/* TAB 3: CROSS-AGENT DEBATE TRANSCRIPT */}
          {activeTab === 'debate' && (
            <div className="space-y-4">
              {!currentSession?.challenge_round?.length ? (
                <div className="bg-[#0f0f1d] border border-slate-800 rounded-2xl p-10 text-center space-y-3">
                  <Activity className="w-10 h-10 text-slate-400 mx-auto" />
                  <h3 className="text-base font-semibold text-slate-300">No Debate Rounds Yet</h3>
                  <p className="text-xs text-slate-400">Run the review board to observe the genuine 2-step cross-agent exchange.</p>
                </div>
              ) : (
                currentSession.challenge_round.map((item, idx) => (
                  <div key={idx} className="bg-[#0f0f1d] border border-slate-800/90 rounded-2xl p-6 shadow-xl space-y-4">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-violet-400">Debate Round #{idx + 1}</span>
                        <span className="text-[10px] bg-violet-500/10 text-violet-300 px-2 py-0.5 rounded font-mono">
                          2-Step Independent Exchange
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">
                          Challenger ({item.challenger_provider || 'mock'}) → Target ({item.target_provider || 'mock'})
                        </span>
                      </div>
                    </div>

                    <div className="text-xs text-slate-300 space-y-2">
                      <p className="font-semibold">{item.challenger_role} → {item.target_role}</p>
                      <span className="text-amber-400">{item.is_simulated ? 'Simulated exchange' : 'Live exchange'}</span>
                      <p className="text-slate-400">Challenge preview — expand for the complete exchange:</p>
                      <p className="line-clamp-3"><strong>Challenge:</strong> {item.challenge_point}</p>
                      <p className="line-clamp-3"><strong>Response preview:</strong> {item.response}</p>
                      <p className="text-emerald-300">Evidence IDs referenced: {currentSession.idea.evidence
                        .filter(evidence => [item.challenge_point, item.response, item.reasoning_adjustment].some(text => text.toUpperCase().includes(`[${evidence.id.toUpperCase()}]`)))
                        .map(evidence => evidence.id).join(', ') || 'None'}</p>
                    </div>
                    <details className="space-y-3 text-xs">
                      <summary className="cursor-pointer font-semibold text-indigo-300">Full challenge, response and reasoning adjustment</summary>
                      {/* Step 1: Challenger */}
                      <div className="bg-red-950/20 border border-red-500/30 p-3.5 rounded-xl space-y-1">
                        <div className="flex items-center justify-between text-red-300 font-bold">
                          <div className="flex items-center gap-1.5">
                            <AlertTriangle className="w-4 h-4" />
                            <span>Step 1: {item.challenger_role} challenges {item.target_role}:</span>
                          </div>
                          <span className="text-[10px] font-mono text-red-400">{item.challenger_provider || 'mock'}</span>
                        </div>
                        <p className="text-slate-200 leading-relaxed pl-5">
                          &ldquo;{item.challenge_point}&rdquo;
                        </p>
                      </div>

                      {/* Step 2: Target Response */}
                      <div className="bg-indigo-950/20 border border-indigo-500/30 p-3.5 rounded-xl space-y-1">
                        <div className="flex items-center justify-between text-indigo-300 font-bold">
                          <div className="flex items-center gap-1.5">
                            <ArrowRight className="w-4 h-4" />
                            <span>Step 2: {item.target_role}&apos;s Independent Defense:</span>
                          </div>
                          <span className="text-[10px] font-mono text-indigo-400">{item.target_provider || 'mock'}</span>
                        </div>
                        <p className="text-slate-200 leading-relaxed pl-5">
                          &ldquo;{item.response}&rdquo;
                        </p>
                      </div>

                      {/* Reasoning Shift */}
                      <div className="bg-emerald-950/20 border border-emerald-500/30 p-3 rounded-xl flex items-start gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                        <div>
                          <strong className="text-emerald-300">Reasoning Shift:</strong>
                          <span className="text-slate-300 ml-1">{item.reasoning_adjustment}</span>
                        </div>
                      </div>
                    </details>
                  </div>
                ))
              )}
            </div>
          )}
        </section>
      </main>

      {/* ── SAVED REVIEWS DRAWER ── */}
      {isHistoryOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md bg-[#0e0e1a] border-l border-slate-800 p-6 flex flex-col justify-between shadow-2xl animate-in slide-in-from-right">
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <History className="w-5 h-5 text-violet-400" />
                  <h3 className="font-bold text-base text-white">Saved Review Sessions</h3>
                </div>
                <button onClick={() => setIsHistoryOpen(false)} className="text-slate-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-2.5 max-h-[70vh] overflow-y-auto pr-1">
                {savedSessions.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">No saved reviews yet.</p>
                ) : (
                  savedSessions.map((s) => (
                    <div
                      key={s.session_id}
                      onClick={() => handleReopenSession(s.session_id)}
                      className="bg-slate-900/90 hover:bg-slate-800/90 border border-slate-800 p-3 rounded-xl cursor-pointer transition text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200 truncate max-w-[200px]">{s.title}</span>
                        <div className="flex items-center gap-1.5">
                          {s.version && s.version > 1 && (
                            <span className="text-[10px] bg-violet-500/20 text-violet-300 px-1 py-0.2 rounded font-mono">
                              v{s.version}
                            </span>
                          )}
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                            s.status === 'completed' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'
                          }`}>
                            {s.status}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-400">
                        <span>{s.specialist_count} specialists • {s.evidence_status}</span>
                        <span>{new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <button
              onClick={() => setIsHistoryOpen(false)}
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-xl transition"
            >
              Close History
            </button>
          </div>
        </div>
      )}

      {/* ── BUDGET & RELIABILITY CONFIG MODAL ── */}
      {showConfigModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-[#0f0f1d] border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-base text-white">Budget & Reliability Controls</h3>
              </div>
              <button onClick={() => setShowConfigModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Call Cap (Hard Stop on all invocations)</label>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={budget.call_cap}
                  onChange={(e) => setBudget({ ...budget, call_cap: parseInt(e.target.value) || 20 })}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-slate-100"
                />
                <span className="text-[10px] text-slate-400">Checked atomically before every call, including retries & debate steps.</span>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Token Cap (Total Budget)</label>
                <input
                  type="number"
                  min={1000}
                  max={200000}
                  step={5000}
                  value={budget.token_cap}
                  onChange={(e) => setBudget({ ...budget, token_cap: parseInt(e.target.value) || 50000 })}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-slate-100"
                />
                <span className="text-[10px] text-slate-400">Reserves estimated tokens prior to request execution.</span>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Per-Call Timeout (seconds)</label>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={budget.timeout_seconds}
                  onChange={(e) => setBudget({ ...budget, timeout_seconds: parseFloat(e.target.value) || 12 })}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-slate-100"
                />
                <span className="text-[10px] text-slate-400">Calls taking longer are interrupted and marked timed_out.</span>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">Max Retries on Transient Error</label>
                <select
                  value={budget.max_retries}
                  onChange={(e) => setBudget({ ...budget, max_retries: parseInt(e.target.value) || 0 })}
                  className="w-full bg-slate-900 border border-slate-800 rounded px-3 py-2 text-slate-100"
                >
                  <option value={0}>0 Retries</option>
                  <option value={1}>1 Retry (Spec Maximum)</option>
                </select>
                <span className="text-[10px] text-slate-400">Bounded to at most 1 retry per agent per prompt spec.</span>
              </div>
            </div>

            <button
              onClick={() => setShowConfigModal(false)}
              className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-xl transition"
            >
              Save Controls
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
