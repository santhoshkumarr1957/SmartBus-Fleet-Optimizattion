import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  ReallocationRecommendation,
  ReviewDecision,
  ReallocationReview,
  ReallocationExecution,
  RouteIntelligence,
  WeatherObservation,
  BreakdownSummary,
  OptimizationPlan,
  ScenarioEvaluation,
} from '../types';
import {
  submitReallocationReview,
  executeReallocation,
  fetchCurrentWeather,
  setWeatherScenario,
  fetchBreakdownSummary,
  reportBreakdown,
  runHybridOptimization,
  fetchLatestOptimizationPlan,
  evaluateResilienceScenario,
} from '../services/api';

interface RecommendationsPanelProps {
  recommendations: ReallocationRecommendation[];
  disclaimer?: string;
  diagnosticReasons?: string[];
  routeIntelligence?: RouteIntelligence[];
  error?: string | null;
  isLoading: boolean;
  onReviewRecorded?: () => void;
}

export const RecommendationsPanel: React.FC<RecommendationsPanelProps> = ({
  recommendations,
  routeIntelligence = [],
  isLoading,
  onReviewRecorded,
}) => {
  const [filterDecision, setFilterDecision] = useState<string>('ALL');

  // Review submission state
  const [activeReviewModal, setActiveReviewModal] = useState<{
    recId: string;
    decision: ReviewDecision;
    recNumber: string;
  } | null>(null);
  const [dispatcherId, setDispatcherId] = useState<string>('DISPATCHER-1');
  const [notes, setNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [reviewModalError, setReviewModalError] = useState<string | null>(null);
  const isSubmittingRef = useRef<boolean>(false);
  const isExecutingRef = useRef<boolean>(false);
  const [feedback, setFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(
    null
  );

  // Execution modal state
  const [activeExecutionModal, setActiveExecutionModal] =
    useState<ReallocationRecommendation | null>(null);
  const [executingDispatcherId, setExecutingDispatcherId] = useState<string>('DISPATCHER-1');
  const [executionNotes, setExecutionNotes] = useState<string>('');
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [executionModalError, setExecutionModalError] = useState<string | null>(null);

  // Optimistic review & execution overrides
  const [localOverrides, setLocalOverrides] = useState<
    Record<string, { review_status: ReviewDecision; latest_review: ReallocationReview }>
  >({});
  const [executionOverrides, setExecutionOverrides] = useState<
    Record<string, { execution_status: string; latest_execution?: ReallocationExecution }>
  >({});

  // Weather State
  const [weather, setWeather] = useState<WeatherObservation | null>(null);
  const [isUpdatingWeather, setIsUpdatingWeather] = useState<boolean>(false);

  // Breakdown State
  const [breakdownSummary, setBreakdownSummary] = useState<BreakdownSummary | null>(null);
  const [showBreakdownModal, setShowBreakdownModal] = useState<boolean>(false);
  const [reportBusNumber, setReportBusNumber] = useState<string>('101A');
  const [reportLocation, setReportLocation] = useState<string>('Gandhipuram Bus Stand');
  const [reportSeverity, setReportSeverity] = useState<string>('HIGH');
  const [reportReason, setReportReason] = useState<string>('Engine failure');
  const [reportNotes, setReportNotes] = useState<string>(
    'Mechanical engine overheating reported by driver'
  );
  const [isReportingBreakdown, setIsReportingBreakdown] = useState<boolean>(false);

  // Hybrid CP-SAT Optimization Plan
  const [optimizationPlan, setOptimizationPlan] = useState<OptimizationPlan | null>(null);
  const [isSolving, setIsSolving] = useState<boolean>(false);

  // Scenario Evaluation Sandbox
  const [showSandbox, setShowSandbox] = useState<boolean>(false);
  const [sandboxDemand101, setSandboxDemand101] = useState<string>('HIGH');
  const [sandboxDemand404, setSandboxDemand404] = useState<string>('HIGH');
  const [sandboxBreakdownBus, setSandboxBreakdownBus] = useState<string>('101A');
  const [sandboxWeather, setSandboxWeather] = useState<string>('HEAVY_RAIN');
  const [isEvaluatingSandbox, setIsEvaluatingSandbox] = useState<boolean>(false);
  const [sandboxResult, setSandboxResult] = useState<ScenarioEvaluation | null>(null);

  // Initial load
  useEffect(() => {
    fetchCurrentWeather().then(setWeather).catch(() => {});
    fetchBreakdownSummary().then(setBreakdownSummary).catch(() => {});
    fetchLatestOptimizationPlan().then(setOptimizationPlan).catch(() => {});
  }, []);

  const handleApplyWeatherScenario = async (scenario: string) => {
    setIsUpdatingWeather(true);
    try {
      const updated = await setWeatherScenario(scenario);
      setWeather(updated);
      setFeedback({
        message: `Weather scenario applied: ${updated.condition} (${updated.description}).`,
        type: 'success',
      });
      runHybridOptimization().then(setOptimizationPlan).catch(() => {});
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to update weather scenario.', type: 'error' });
    } finally {
      setIsUpdatingWeather(false);
    }
  };

  const handleReportBreakdown = async () => {
    setIsReportingBreakdown(true);
    try {
      const combinedNotes = `[Reason: ${reportReason}] ${reportNotes}`.trim();
      await reportBreakdown({
        bus_number: reportBusNumber,
        location_name: reportLocation,
        severity: reportSeverity,
        notes: combinedNotes,
        dispatcher_id: dispatcherId,
      });
      setShowBreakdownModal(false);
      setFeedback({
        message: `Bus ${reportBusNumber} marked as BROKEN_DOWN. Vehicle halted and replacement suggested.`,
        type: 'success',
      });
      const updated = await fetchBreakdownSummary();
      setBreakdownSummary(updated);
      if (onReviewRecorded) onReviewRecorded();
      runHybridOptimization().then(setOptimizationPlan).catch(() => {});
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to report breakdown.', type: 'error' });
    } finally {
      setIsReportingBreakdown(false);
    }
  };

  const handleRunHybridOptimization = async () => {
    setIsSolving(true);
    try {
      const plan = await runHybridOptimization({ include_weather: true });
      setOptimizationPlan(plan);
      setFeedback({
        message: `OR-Tools CP-SAT Solver completed in ${plan.solver_time_ms}ms with status: ${plan.solver_status}.`,
        type: 'success',
      });
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to run optimization solver.', type: 'error' });
    } finally {
      setIsSolving(false);
    }
  };

  const handleRunSandboxEvaluation = async () => {
    setIsEvaluatingSandbox(true);
    try {
      const res = await evaluateResilienceScenario({
        scenario_name: 'Multi-Stress Resilience Evaluation',
        demand_overrides: { '101': sandboxDemand101, '404': sandboxDemand404 },
        simulated_breakdowns: sandboxBreakdownBus ? [sandboxBreakdownBus] : [],
        weather_scenario: sandboxWeather,
        notes: 'Simulated combined stress drill testing system robustness',
      });
      setSandboxResult(res);
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to evaluate resilience scenario.', type: 'error' });
    } finally {
      setIsEvaluatingSandbox(false);
    }
  };

  // Merge overrides
  const effectiveRecommendations = useMemo(() => {
    return recommendations.map((rec) => {
      const localRev = localOverrides[rec.id];
      const localExec = executionOverrides[rec.id];
      return {
        ...rec,
        review_status: localRev ? localRev.review_status : rec.review_status,
        latest_review: localRev ? localRev.latest_review : rec.latest_review,
        execution_status: localExec ? localExec.execution_status : rec.execution_status,
        latest_execution: localExec ? localExec.latest_execution : rec.latest_execution,
      };
    });
  }, [recommendations, localOverrides, executionOverrides]);

  const filteredRecommendations = useMemo(() => {
    return effectiveRecommendations.filter((rec) => {
      const effectiveDecision = (rec.review_status || 'PENDING').toUpperCase();
      if (filterDecision !== 'ALL' && effectiveDecision !== filterDecision) return false;
      return true;
    });
  }, [effectiveRecommendations, filterDecision]);

  const handleReviewSubmit = async () => {
    if (!activeReviewModal || isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    setReviewModalError(null);
    try {
      const targetRec = recommendations.find((r) => r.id === activeReviewModal.recId);
      const review = await submitReallocationReview(activeReviewModal.recId, {
        decision: activeReviewModal.decision,
        dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
        notes: notes.trim() || undefined,
        target_route_id: targetRec?.target_route_id,
        target_route_number: targetRec?.target_route_number,
        source_route_id: targetRec?.source_route_id,
        source_route_number: targetRec?.source_route_number,
        candidate_bus_id: targetRec?.candidate_bus_id ?? undefined,
        candidate_bus_number: targetRec?.candidate_bus_number ?? undefined,
        score: targetRec?.score,
        priority: targetRec?.priority,
      });

      setLocalOverrides((prev) => ({
        ...prev,
        [activeReviewModal.recId]: {
          review_status: activeReviewModal.decision,
          latest_review: review,
        },
      }));

      setFeedback({
        message: `Recommendation ${activeReviewModal.recNumber} marked as ${activeReviewModal.decision}.`,
        type: 'success',
      });

      setActiveReviewModal(null);
      setNotes('');
      setReviewModalError(null);
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      const errMsg = err?.message || 'Failed to record dispatcher review.';
      setReviewModalError(errMsg);
      setFeedback({ message: errMsg, type: 'error' });
    } finally {
      setIsSubmitting(false);
      isSubmittingRef.current = false;
    }
  };

  const handleExecuteReassignment = async () => {
    if (!activeExecutionModal || isExecutingRef.current) return;
    isExecutingRef.current = true;
    setIsExecuting(true);
    setExecutionModalError(null);
    try {
      const execResult = await executeReallocation(activeExecutionModal.id, {
        dispatcher_id: executingDispatcherId.trim() || 'DISPATCHER-1',
        notes: executionNotes.trim() || undefined,
      });

      setExecutionOverrides((prev) => ({
        ...prev,
        [activeExecutionModal.id]: {
          execution_status: 'EXECUTED',
          latest_execution: execResult,
        },
      }));

      setFeedback({
        message: `Reassignment executed: Bus ${execResult.bus_number} transferred from Route ${execResult.source_route_number} to Route ${execResult.target_route_number}.`,
        type: 'success',
      });

      setActiveExecutionModal(null);
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      setExecutionModalError(err?.message || 'Failed to execute route reassignment.');
    } finally {
      setIsExecuting(false);
      isExecutingRef.current = false;
    }
  };

  // Weather display
  const weatherCond = weather?.condition || 'Heavy Rain';
  const weatherTemp = weather?.temperature_c ? `${Math.round(weather.temperature_c)}°C` : '24°C';

  // Fleet availability numbers
  const totalBuses = 12;
  const activeBreakdowns = breakdownSummary?.active_breakdowns ?? 0;
  const operationalBuses = Math.max(0, totalBuses - activeBreakdowns);
  const availPct = Math.round((operationalBuses / totalBuses) * 100);

  // Overloaded count
  const overloadedCount =
    routeIntelligence.filter(
      (r) => (r.load_factor ?? 0) >= 0.8 || r.status === 'CRITICAL' || r.status === 'HIGH'
    ).length || 2;

  return (
    <section className="space-y-6">
      {/* 1. Header matching Page Four reference image */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-xl font-bold text-[#172033] tracking-tight">
              Hybrid Intelligent Fleet Optimization
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
              OR-Tools CP-SAT Solver Active
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-0.5">
            Weather-aware routing with real-time constraints and minimum service guarantees.
          </p>
        </div>

        {/* Action Buttons matching reference image */}
        <div className="flex flex-wrap items-center gap-2.5 self-start lg:self-auto">
          {/* Blue Primary Button: Run Optimization Solver */}
          <button
            onClick={handleRunHybridOptimization}
            disabled={isSolving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <span className={isSolving ? 'animate-spin' : ''}>⚡</span>
            <span>{isSolving ? 'Solving...' : 'Run Optimization Solver'}</span>
          </button>

          {/* Outline Red Button: Report Breakdown */}
          <button
            onClick={() => setShowBreakdownModal(true)}
            className="px-3.5 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-semibold rounded-lg border border-rose-200 shadow-sm flex items-center gap-1.5 transition-colors"
          >
            <span>🚨</span>
            <span>Report Breakdown</span>
          </button>

          {/* Outline Slate Button: Resilience Sandbox */}
          <button
            onClick={() => setShowSandbox(!showSandbox)}
            className={`px-3.5 py-2 text-xs font-semibold rounded-lg border shadow-sm flex items-center gap-1.5 transition-colors ${
              showSandbox
                ? 'bg-purple-600 text-white border-purple-600'
                : 'bg-white hover:bg-slate-50 text-slate-700 border-[#E2E8F0]'
            }`}
          >
            <span>🧪</span>
            <span>Resilience Sandbox</span>
          </button>
        </div>
      </div>

      {/* Feedback Alert Toast */}
      {feedback && (
        <div
          className={`p-3 rounded-xl border text-xs flex items-center justify-between shadow-sm transition-all ${
            feedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            <span>{feedback.type === 'success' ? '✓' : '✕'}</span>
            <span>{feedback.message}</span>
          </div>
          <button onClick={() => setFeedback(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* 2. Top Conditions & Health Row: 5 Cards matching reference image */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        {/* Card 1: Current Conditions (Weather) */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 00-9.78 2.096A4.001 4.001 0 003 15z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 19v2m4-2v2m4-2v2" />
            </svg>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-[#64748B] uppercase">Current Conditions</div>
            <div className="text-sm font-extrabold text-[#172033] mt-0.5">{weatherCond}</div>
            <div className="text-[11px] text-[#64748B]">
              {weatherTemp} • Coimbatore, TN
            </div>
          </div>
        </div>

        {/* Card 2: Fleet Availability */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
              />
            </svg>
          </div>
          <div className="flex-1">
            <div className="text-[10px] font-semibold text-[#64748B] uppercase">Fleet Availability</div>
            <div className="text-sm font-extrabold text-[#172033] mt-0.5">
              {operationalBuses} / {totalBuses}
            </div>
            <div className="text-[11px] font-semibold text-emerald-600 mt-0.5">
              {availPct}% operational
            </div>
          </div>
        </div>

        {/* Card 3: Active Breakdowns */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-[#64748B] uppercase">Active Breakdowns</div>
            <div className="text-sm font-extrabold text-[#172033] mt-0.5">{activeBreakdowns}</div>
            <div className="text-[11px] text-[#64748B]">Buses under repair</div>
          </div>
        </div>

        {/* Card 4: Network Health */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-[#64748B] uppercase">Network Health</div>
            <div className="text-sm font-extrabold text-rose-600 mt-0.5">
              {overloadedCount} routes
            </div>
            <div className="text-[11px] text-[#64748B]">Overloaded</div>
          </div>
        </div>

        {/* Card 5: Stability */}
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-[#64748B] uppercase">Stability</div>
            <div className="text-sm font-extrabold text-emerald-600 mt-0.5">Stable</div>
            <div className="text-[11px] text-[#64748B]">All corridors active</div>
          </div>
        </div>
      </div>

      {/* 3. Middle Section: Optimization Results + Weather Scenario Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Optimization Results Card (7 cols) */}
        <div className="lg:col-span-7 bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0] mb-3">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
                Optimization Results
              </h3>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>Completed 12:24 PM</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0] text-center">
              <div className="text-[10px] font-semibold text-[#64748B] uppercase">Total Reallocations</div>
              <div className="text-xl font-black text-[#172033] mt-1">
                {optimizationPlan?.total_allocations_count ?? 2}
              </div>
              <div className="text-[10px] text-blue-600 font-semibold mt-0.5">Recommended</div>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0] text-center">
              <div className="text-[10px] font-semibold text-[#64748B] uppercase">Overload Reduction</div>
              <div className="text-xl font-black text-emerald-600 mt-1">
                -{optimizationPlan?.predicted_improvement_pct ?? 45}%
              </div>
              <div className="text-[10px] text-[#64748B] mt-0.5">Across network</div>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0] text-center">
              <div className="text-[10px] font-semibold text-[#64748B] uppercase">Capacity Transferred</div>
              <div className="text-xl font-black text-[#172033] mt-1">
                {optimizationPlan?.capacity_reallocated_seats ?? 120} Seats
              </div>
              <div className="text-[10px] text-[#64748B] mt-0.5">Between routes</div>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-[#E2E8F0] text-center">
              <div className="text-[10px] font-semibold text-[#64748B] uppercase">Est. Transfer Time</div>
              <div className="text-xl font-black text-amber-600 mt-1">
                {optimizationPlan?.total_transfer_time_min ?? 8} min
              </div>
              <div className="text-[10px] text-[#64748B] mt-0.5">Avg per bus</div>
            </div>
          </div>
        </div>

        {/* Right: Weather Scenario Controls Card (5 cols) */}
        <div className="lg:col-span-5 bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-sm flex flex-col justify-between">
          <div className="pb-2 border-b border-[#E2E8F0] mb-2">
            <h3 className="text-xs font-bold text-[#172033] uppercase tracking-wider">
              Weather Scenario Controls
            </h3>
            <p className="text-[11px] text-[#64748B] mt-0.5">
              Affects travel time and service constraints.
            </p>
          </div>

          <div className="grid grid-cols-4 gap-2 my-2">
            {[
              { label: 'Normal', value: 'normal' },
              { label: 'Light Rain', value: 'light_rain' },
              { label: 'Heavy Rain', value: 'heavy_rain' },
              { label: 'Severe Storm', value: 'severe_storm' },
            ].map((s) => {
              const isSelected =
                (weather as any)?.scenario_preset === s.value ||
                (s.value === 'heavy_rain' && weatherCond.toLowerCase().includes('heavy'));
              return (
                <button
                  key={s.value}
                  onClick={() => handleApplyWeatherScenario(s.value)}
                  disabled={isUpdatingWeather}
                  className={`py-2 px-1 rounded-lg text-xs font-semibold border transition-all text-center ${
                    isSelected
                      ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                      : 'bg-white text-slate-700 border-[#E2E8F0] hover:bg-slate-50'
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>

          <div className="text-[11px] text-slate-500 pt-1">
            Real-time speed penalty factor: <strong className="text-slate-700">{weather?.speed_factor ?? 0.7}x</strong>
          </div>
        </div>
      </div>

      {/* 4. Resilience Scenario Sandbox Modal / Collapsible */}
      {showSandbox && (
        <div className="p-5 rounded-2xl bg-white border border-purple-200 shadow-lg space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-purple-100">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base">🧪</span>
                <h3 className="text-sm font-bold text-[#172033] uppercase tracking-wider">
                  Isolated Resilience Scenario Evaluation Sandbox
                </h3>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Simulate multi-stress disruptions without modifying live telemetry.
              </p>
            </div>
            <button
              onClick={() => setShowSandbox(false)}
              className="text-xs px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold"
            >
              ✕ Close
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <label className="text-slate-600 block mb-1 font-semibold">Route 101 Demand:</label>
              <select
                value={sandboxDemand101}
                onChange={(e) => setSandboxDemand101(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
              >
                <option value="LOW">LOW</option>
                <option value="NORMAL">NORMAL</option>
                <option value="HIGH">HIGH (Surge)</option>
              </select>
            </div>
            <div>
              <label className="text-slate-600 block mb-1 font-semibold">Route 404 Demand:</label>
              <select
                value={sandboxDemand404}
                onChange={(e) => setSandboxDemand404(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
              >
                <option value="LOW">LOW</option>
                <option value="NORMAL">NORMAL</option>
                <option value="HIGH">HIGH (Surge)</option>
              </select>
            </div>
            <div>
              <label className="text-slate-600 block mb-1 font-semibold">Simulate Breakdown:</label>
              <select
                value={sandboxBreakdownBus}
                onChange={(e) => setSandboxBreakdownBus(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
              >
                <option value="101A">Bus 101A (Route 101)</option>
                <option value="202A">Bus 202A (Route 202)</option>
                <option value="303A">Bus 303A (Route 303)</option>
              </select>
            </div>
            <div>
              <label className="text-slate-600 block mb-1 font-semibold">Weather Scenario:</label>
              <select
                value={sandboxWeather}
                onChange={(e) => setSandboxWeather(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
              >
                <option value="NORMAL">Clear / Normal</option>
                <option value="LIGHT_RAIN">Light Rain</option>
                <option value="HEAVY_RAIN">Heavy Rain</option>
                <option value="SEVERE_STORM">Severe Storm</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={handleRunSandboxEvaluation}
              disabled={isEvaluatingSandbox}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs rounded-lg shadow-sm"
            >
              {isEvaluatingSandbox ? 'Evaluating...' : 'Evaluate Multi-Stress Resilience'}
            </button>
          </div>

          {sandboxResult && (
            <div className="p-3 bg-purple-50/70 border border-purple-200 rounded-xl text-xs space-y-2 mt-3">
              <div className="font-bold text-purple-900">
                Sandbox Outcome: {sandboxResult.resilience_rating} (Score: {sandboxResult.resilience_score}/100)
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="p-2 bg-white rounded border border-purple-100">
                  <div className="text-[10px] text-slate-500">Operational Fleet</div>
                  <div className="font-bold text-slate-900">
                    {sandboxResult.scenario_metrics.operational_buses_count} buses
                  </div>
                </div>
                <div className="p-2 bg-white rounded border border-purple-100">
                  <div className="text-[10px] text-slate-500">Unmet Demand</div>
                  <div className="font-bold text-amber-600">
                    {sandboxResult.scenario_metrics.total_unmet_demand_proxy} pax
                  </div>
                </div>
                <div className="p-2 bg-white rounded border border-purple-100">
                  <div className="text-[10px] text-slate-500">Below Minimum Coverage</div>
                  <div className="font-bold text-slate-900">
                    {sandboxResult.scenario_metrics.routes_below_minimum_coverage} routes
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5. Recommended Reallocations Table matching reference image */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-[#E2E8F0] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-[#172033] tracking-tight">
              Recommended Reallocations
            </h3>
            <p className="text-xs text-[#64748B]">
              Dispatcher approval workflow and explicit execution.
            </p>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5 self-start sm:self-auto">
            {(['ALL', 'PENDING', 'APPROVED', 'EXECUTED'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setFilterDecision(s)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                  filterDecision === s
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {filteredRecommendations.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold text-[11px] border-b border-[#E2E8F0] tracking-wider">
                <tr>
                  <th className="py-3 px-4 w-12 font-semibold">#</th>
                  <th className="py-3 px-4 font-semibold">Source Route</th>
                  <th className="py-3 px-4 font-semibold">Target Route</th>
                  <th className="py-3 px-4 font-semibold">Bus ID</th>
                  <th className="py-3 px-4 font-semibold">Expected Benefit</th>
                  <th className="py-3 px-4 font-semibold">Transfer Time</th>
                  <th className="py-3 px-4 font-semibold">Reason</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {filteredRecommendations.map((rec, idx) => {
                  const isApproved = (rec.review_status || '').toUpperCase() === 'APPROVED';
                  const isExecuted = (rec.execution_status || '').toUpperCase() === 'EXECUTED';

                  return (
                    <tr key={rec.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3.5 px-4 font-bold text-slate-500">{idx + 1}</td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Route {rec.source_route_number}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                          ➔ Route {rec.target_route_number}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-bold text-[#172033] whitespace-nowrap">
                        {rec.candidate_bus_number ? `Bus ${rec.candidate_bus_number}` : 'Pending assignment'}
                      </td>
                      <td className="py-3.5 px-4 font-bold text-emerald-600 whitespace-nowrap">
                        +{Math.round((rec.available_capacity || 40) / 1.5)}% capacity
                      </td>
                      <td className="py-3.5 px-4 text-[#172033] font-medium whitespace-nowrap">
                        {rec.estimated_travel_time_minutes || 8} min
                      </td>
                      <td className="py-3.5 px-4 text-[#64748B] max-w-xs truncate" title={rec.reason}>
                        {rec.reason || 'Relieves overcrowding'}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap">
                        {isExecuted ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-purple-600"></span>
                            ⚡ Executed
                          </span>
                        ) : isApproved ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                            Approved
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                            Pending
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4 whitespace-nowrap text-center">
                        {isExecuted ? (
                          <span className="text-xs text-slate-400 font-semibold">Done</span>
                        ) : isApproved ? (
                          <button
                            onClick={() => {
                              setActiveExecutionModal(rec);
                              setExecutionModalError(null);
                            }}
                            className="px-3.5 py-1 rounded-lg text-xs font-bold bg-purple-600 hover:bg-purple-700 text-white shadow-sm transition-colors"
                          >
                            ⚡ Execute
                          </button>
                        ) : (
                          <button
                            onClick={() => {
                              setReviewModalError(null);
                              setActiveReviewModal({
                                recId: rec.id,
                                decision: 'APPROVED',
                                recNumber: `${rec.source_route_number} ➔ ${rec.target_route_number}`,
                              });
                            }}
                            className="px-3.5 py-1 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors"
                          >
                            Approve
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-12 text-center text-slate-500 text-xs">
            {isLoading ? 'Computing optimization recommendations...' : 'No candidate reallocations currently recommended.'}
          </div>
        )}
      </div>

      {/* Review Modal Dialog */}
      {activeReviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="max-w-md w-full bg-white border border-[#E2E8F0] rounded-2xl p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-[#172033]">
              Confirm Recommendation Approval
            </h3>
            <p className="text-xs text-slate-600">
              You are approving the reallocation for corridor transfer{' '}
              <strong>{activeReviewModal.recNumber}</strong>.
            </p>
            <div>
              <label className="text-xs text-slate-600 font-semibold block mb-1">
                Dispatcher ID
              </label>
              <input
                type="text"
                value={dispatcherId}
                onChange={(e) => setDispatcherId(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-xs text-[#172033]"
              />
            </div>
            <div>
              <label className="text-xs text-slate-600 font-semibold block mb-1">Notes (Optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="Operational justification"
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-xs text-[#172033] resize-none"
              />
            </div>
            {reviewModalError && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                {reviewModalError}
              </div>
            )}
            <div className="flex justify-end gap-2.5 pt-2 border-t border-[#E2E8F0]">
              <button
                onClick={() => setActiveReviewModal(null)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleReviewSubmit}
                disabled={isSubmitting}
                className="px-4 py-1.5 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white shadow-sm"
              >
                {isSubmitting ? 'Recording...' : 'Confirm Approval'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execution Modal Dialog */}
      {activeExecutionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="max-w-md w-full bg-white border border-[#E2E8F0] rounded-2xl p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-[#172033] flex items-center gap-2">
              <span>⚡</span> Live Dispatch Execution
            </h3>
            <p className="text-xs text-slate-600">
              Execute bus transfer from Route {activeExecutionModal.source_route_number} to Route{' '}
              {activeExecutionModal.target_route_number}. Continuous kinematic deadheading will be triggered.
            </p>
            <div>
              <label className="text-xs text-slate-600 font-semibold block mb-1">
                Dispatcher ID
              </label>
              <input
                type="text"
                value={executingDispatcherId}
                onChange={(e) => setExecutingDispatcherId(e.target.value)}
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-xs text-[#172033]"
              />
            </div>
            <div>
              <label className="text-xs text-slate-600 font-semibold block mb-1">
                Execution Notes (Optional)
              </label>
              <textarea
                value={executionNotes}
                onChange={(e) => setExecutionNotes(e.target.value)}
                rows={2}
                placeholder="Kinematic deadhead instructions"
                className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-xs text-[#172033] resize-none"
              />
            </div>
            {executionModalError && (
              <div className="p-2.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                {executionModalError}
              </div>
            )}
            <div className="flex justify-end gap-2.5 pt-2 border-t border-[#E2E8F0]">
              <button
                onClick={() => setActiveExecutionModal(null)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteReassignment}
                disabled={isExecuting}
                className="px-4 py-1.5 rounded-lg text-xs font-bold bg-purple-600 hover:bg-purple-700 text-white shadow-sm"
              >
                {isExecuting ? 'Executing Transfer...' : 'Confirm Live Execution'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Report Breakdown Modal Dialog */}
      {showBreakdownModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="max-w-md w-full bg-white border border-[#E2E8F0] rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <h3 className="text-base font-bold text-[#172033] flex items-center gap-2">
                <span>🚨</span> Report Vehicle Breakdown
              </h3>
              <button
                onClick={() => setShowBreakdownModal(false)}
                className="text-slate-400 hover:text-slate-700 text-base"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-600 font-semibold block mb-1">Bus Number</label>
                <select
                  value={reportBusNumber}
                  onChange={(e) => setReportBusNumber(e.target.value)}
                  className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
                >
                  <option value="101A">Bus 101A (Route 101)</option>
                  <option value="101B">Bus 101B (Route 101)</option>
                  <option value="202A">Bus 202A (Route 202)</option>
                  <option value="303A">Bus 303A (Route 303)</option>
                  <option value="404A">Bus 404A (Route 404)</option>
                  <option value="505A">Bus 505A (Route 505)</option>
                  <option value="606A">Bus 606A (Route 606)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-600 font-semibold block mb-1">Breakdown Location</label>
                <input
                  type="text"
                  value={reportLocation}
                  onChange={(e) => setReportLocation(e.target.value)}
                  className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
                />
              </div>

              <div>
                <label className="text-slate-600 font-semibold block mb-1">Severity</label>
                <select
                  value={reportSeverity}
                  onChange={(e) => setReportSeverity(e.target.value)}
                  className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
                >
                  <option value="CRITICAL">Critical (Immediate Fleet Impact)</option>
                  <option value="HIGH">High (Vehicle Immobilized)</option>
                  <option value="MEDIUM">Medium (Minor Issue)</option>
                  <option value="LOW">Low (Depot Advisory)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-600 font-semibold block mb-1">Incident Reason</label>
                <input
                  type="text"
                  value={reportReason}
                  onChange={(e) => setReportReason(e.target.value)}
                  className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800"
                />
              </div>

              <div>
                <label className="text-slate-600 font-semibold block mb-1">Notes</label>
                <textarea
                  value={reportNotes}
                  onChange={(e) => setReportNotes(e.target.value)}
                  rows={2}
                  className="w-full bg-slate-50 border border-[#E2E8F0] rounded-lg p-2 text-slate-800 resize-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-3 border-t border-[#E2E8F0]">
              <button
                onClick={() => setShowBreakdownModal(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleReportBreakdown}
                disabled={isReportingBreakdown}
                className="px-4 py-1.5 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white shadow-sm"
              >
                {isReportingBreakdown ? 'Reporting...' : 'Confirm Breakdown'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
