import React, { useState, useEffect, useMemo } from 'react';
import {
  ReallocationRecommendation,
  ReviewDecision,
  ReallocationReview,
  ReallocationExecution,
  RouteIntelligence,
  WeatherObservation,
  BreakdownSummary,
  ReplacementCandidate,
  OptimizationPlan,
  ScenarioEvaluation,
} from '../types';
import { StatusBadge } from './StatusBadge';
import {
  submitReallocationReview,
  fetchRecommendationHistory,
  executeReallocation,
  fetchRecommendationExecutions,
  fetchCurrentWeather,
  setWeatherScenario,
  fetchBreakdownSummary,
  reportBreakdown,
  updateBreakdownStatus,
  fetchReplacementCandidates,
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
  disclaimer,
  diagnosticReasons = [],
  routeIntelligence = [],
  error = null,
  isLoading,
  onReviewRecorded,
}) => {
  const [filterPriority, setFilterPriority] = useState<string>('ALL');
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
  const [feedback, setFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(
    null
  );

  // Execution modal state (Explicit execution action)
  const [activeExecutionModal, setActiveExecutionModal] = useState<ReallocationRecommendation | null>(
    null
  );
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

  // History inspection drawer state
  const [activeHistoryRecId, setActiveHistoryRecId] = useState<string | null>(null);
  const [historyRecords, setHistoryRecords] = useState<ReallocationReview[]>([]);
  const [historyExecutionRecords, setHistoryExecutionRecords] = useState<ReallocationExecution[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Phase 3: Weather State & Scenario Testing
  // ---------------------------------------------------------------------------
  const [weather, setWeather] = useState<WeatherObservation | null>(null);
  const [isUpdatingWeather, setIsUpdatingWeather] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Phase 4: Breakdown State & Management
  // ---------------------------------------------------------------------------
  const [breakdownSummary, setBreakdownSummary] = useState<BreakdownSummary | null>(null);
  const [showBreakdownModal, setShowBreakdownModal] = useState<boolean>(false);
  const [reportBusNumber, setReportBusNumber] = useState<string>('101A');
  const [reportLocation, setReportLocation] = useState<string>('Gandhipuram Bus Stand');
  const [reportSeverity, setReportSeverity] = useState<string>('HIGH');
  const [reportReason, setReportReason] = useState<string>('Engine failure');
  const [reportNotes, setReportNotes] = useState<string>('Mechanical engine overheating reported by driver');
  const [isReportingBreakdown, setIsReportingBreakdown] = useState<boolean>(false);

  // Replacement candidate inspection modal
  const [replacementModal, setReplacementModal] = useState<ReplacementCandidate | null>(null);
  const [isLoadingReplacement, setIsLoadingReplacement] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Phase 1, 2, 6: Hybrid CP-SAT Optimization Plan
  // ---------------------------------------------------------------------------
  const [optimizationPlan, setOptimizationPlan] = useState<OptimizationPlan | null>(null);
  const [isSolving, setIsSolving] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Phase 5: Scenario Evaluation Sandbox
  // ---------------------------------------------------------------------------
  const [showSandbox, setShowSandbox] = useState<boolean>(false);
  const [sandboxDemand101, setSandboxDemand101] = useState<string>('HIGH');
  const [sandboxDemand404, setSandboxDemand404] = useState<string>('HIGH');
  const [sandboxBreakdownBus, setSandboxBreakdownBus] = useState<string>('101A');
  const [sandboxWeather, setSandboxWeather] = useState<string>('HEAVY_RAIN');
  const [isEvaluatingSandbox, setIsEvaluatingSandbox] = useState<boolean>(false);
  const [sandboxResult, setSandboxResult] = useState<ScenarioEvaluation | null>(null);

  // Initial load of weather, breakdown summary, and latest plan
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
        message: `Weather updated: ${updated.condition} (${updated.description}). Operational speed factor: ${updated.speed_factor}x.`,
        type: 'success',
      });
      // Re-run optimization with new weather context
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
        message: `Bus ${reportBusNumber} marked BROKEN_DOWN (${reportReason}). Vehicle removed from available fleet and halted in simulator.`,
        type: 'success',
      });
      const updated = await fetchBreakdownSummary();
      setBreakdownSummary(updated);
      if (onReviewRecorded) onReviewRecorded();
      // Re-solve optimization to account for broken down vehicle
      runHybridOptimization().then(setOptimizationPlan).catch(() => {});
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to report breakdown.', type: 'error' });
    } finally {
      setIsReportingBreakdown(false);
    }
  };

  const handleUpdateBreakdownLifecycle = async (
    incidentId: number,
    targetStatus: 'CONFIRMED' | 'UNDER_REPAIR' | 'AVAILABLE',
    busNumber: string
  ) => {
    try {
      await updateBreakdownStatus(incidentId, targetStatus, `Updated by dispatcher`, dispatcherId);
      const updated = await fetchBreakdownSummary();
      setBreakdownSummary(updated);
      setFeedback({
        message: `Incident #${incidentId} (Bus ${busNumber}) updated to ${targetStatus}.${targetStatus === 'AVAILABLE' ? ' Vehicle restored to active service.' : ''}`,
        type: 'success',
      });
      if (onReviewRecorded) onReviewRecorded();
      runHybridOptimization().then(setOptimizationPlan).catch(() => {});
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to update incident status.', type: 'error' });
    }
  };

  const handleInspectReplacement = async (busId: number) => {
    setIsLoadingReplacement(true);
    try {
      const res = await fetchReplacementCandidates(busId);
      setReplacementModal(res);
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to fetch replacement candidates.', type: 'error' });
    } finally {
      setIsLoadingReplacement(false);
    }
  };

  const handleRunHybridOptimization = async () => {
    setIsSolving(true);
    try {
      const plan = await runHybridOptimization({ include_weather: true });
      setOptimizationPlan(plan);
      setFeedback({
        message: `Google OR-Tools CP-SAT Solver evaluated ${plan.total_allocations_count} allocation(s) in ${plan.solver_time_ms}ms with status: ${plan.solver_status}.`,
        type: 'success',
      });
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to solve hybrid optimization model.', type: 'error' });
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

  // Merge optimistic overrides with incoming recommendation stream
  const effectiveRecommendations = useMemo(() => {
    return recommendations.map((rec) => {
      let r = { ...rec };
      if (localOverrides[rec.id]) {
        r.review_status = localOverrides[rec.id].review_status;
        r.latest_review = localOverrides[rec.id].latest_review;
      }
      if (executionOverrides[rec.id]) {
        r.execution_status = executionOverrides[rec.id].execution_status;
        r.latest_execution = executionOverrides[rec.id].latest_execution;
      }
      return r;
    });
  }, [recommendations, localOverrides, executionOverrides]);

  // Filtering
  const filteredRecommendations = useMemo(() => {
    return effectiveRecommendations.filter((r) => {
      if (filterPriority !== 'ALL' && r.priority.toUpperCase() !== filterPriority.toUpperCase()) {
        return false;
      }
      const effectiveDecision = (r.review_status || 'PENDING').toUpperCase();
      if (filterDecision !== 'ALL') {
        if (filterDecision === 'PENDING' && r.review_status && r.review_status.toUpperCase() !== 'PENDING') {
          return false;
        }
        if (filterDecision !== 'PENDING' && effectiveDecision !== filterDecision.toUpperCase()) {
          return false;
        }
      }
      return true;
    });
  }, [effectiveRecommendations, filterPriority, filterDecision]);

  const handleOpenReview = (rec: ReallocationRecommendation, decision: ReviewDecision) => {
    setActiveReviewModal({
      recId: rec.id,
      decision,
      recNumber: `${rec.source_route_number} → ${rec.target_route_number}`,
    });
    setNotes('');
    setFeedback(null);
  };

  const handleConfirmReview = async () => {
    if (!activeReviewModal) return;
    setIsSubmitting(true);
    setFeedback(null);

    try {
      const savedReview = await submitReallocationReview(activeReviewModal.recId, {
        decision: activeReviewModal.decision,
        dispatcher_id: dispatcherId.trim() || 'DISPATCHER-1',
        notes: notes.trim() || undefined,
      });

      setLocalOverrides((prev) => ({
        ...prev,
        [activeReviewModal.recId]: {
          review_status: savedReview.decision,
          latest_review: savedReview,
        },
      }));

      setFeedback({
        message: `Decision recorded: Recommendation ${activeReviewModal.recId} marked as ${savedReview.decision}. Vehicle route assignments remain unchanged until explicitly executed.`,
        type: 'success',
      });

      setActiveReviewModal(null);
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      setFeedback({ message: err?.message || 'Failed to record dispatcher review decision.', type: 'error' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenExecute = (rec: ReallocationRecommendation) => {
    setActiveExecutionModal(rec);
    setExecutingDispatcherId(dispatcherId || 'DISPATCHER-1');
    setExecutionNotes('');
    setExecutionModalError(null);
    setFeedback(null);
  };

  const handleConfirmExecute = async () => {
    if (!activeExecutionModal || isExecuting) return;
    setIsExecuting(true);
    setExecutionModalError(null);
    setFeedback(null);

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
        message: `Reassignment executed: Bus ${execResult.bus_number} successfully transferred from Route ${execResult.source_route_number} to Route ${execResult.target_route_number}. Database updated and runtime deadhead transfer initiated.`,
        type: 'success',
      });

      setActiveExecutionModal(null);
      if (onReviewRecorded) onReviewRecorded();
    } catch (err: any) {
      const errorMsg = err?.message || 'Failed to execute route reassignment.';
      setExecutionModalError(errorMsg);
      setFeedback({ message: errorMsg, type: 'error' });
    } finally {
      setIsExecuting(false);
    }
  };

  const handleViewHistory = async (recId: string) => {
    setActiveHistoryRecId(recId);
    setIsLoadingHistory(true);
    try {
      const [reviewData, execData] = await Promise.all([
        fetchRecommendationHistory(recId).catch(() => []),
        fetchRecommendationExecutions(recId).catch(() => []),
      ]);
      setHistoryRecords(reviewData);
      setHistoryExecutionRecords(execData);
    } catch {
      setHistoryRecords([]);
      setHistoryExecutionRecords([]);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  return (
    <section className="mb-8 space-y-6">
      {/* --------------------------------------------------------------------- */}
      {/* 1. Header & Primary Optimization Controls                             */}
      {/* --------------------------------------------------------------------- */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-5 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/95 to-slate-950 border border-slate-800 shadow-xl">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-xl font-extrabold text-white tracking-tight flex items-center gap-2">
              <span>⚡</span> Hybrid Intelligent Fleet Optimization
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-500/15 text-blue-400 font-mono font-bold border border-blue-500/30">
              OR-Tools CP-SAT Solver Active
            </span>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 font-mono font-bold border border-emerald-500/30">
              Weather-Aware Routing
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Deterministic candidate filtering paired with Google OR-Tools CP-SAT mixed-integer constraint optimization.
            Incorporates real-time weather travel penalties, breakdown isolation, and minimum service coverage guarantees.
          </p>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleRunHybridOptimization}
            disabled={isSolving}
            className="px-4 py-2.5 text-xs font-bold text-white bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 active:from-blue-700 active:to-indigo-700 rounded-xl shadow-lg shadow-blue-900/40 border border-blue-400/30 transition-all flex items-center gap-2 disabled:opacity-50"
          >
            <span className={`w-3.5 h-3.5 ${isSolving ? 'animate-spin' : ''}`}>⚡</span>
            {isSolving ? 'Solving CP-SAT Model...' : 'Run Optimization Solver'}
          </button>

          <button
            onClick={() => setShowBreakdownModal(true)}
            className="px-3.5 py-2.5 text-xs font-semibold text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 rounded-xl transition-colors flex items-center gap-1.5"
          >
            <span>🚨</span>
            Report Breakdown
          </button>

          <button
            onClick={() => setShowSandbox(!showSandbox)}
            className={`px-3.5 py-2.5 text-xs font-semibold rounded-xl border transition-colors flex items-center gap-1.5 ${
              showSandbox
                ? 'bg-purple-600 text-white border-purple-500'
                : 'bg-slate-800 text-purple-300 border-purple-500/30 hover:bg-slate-700'
            }`}
          >
            <span>🧪</span>
            Resilience Sandbox
          </button>
        </div>
      </div>

      {/* Confirmation / Error Toast Feedback */}
      {error && (
        <div className="p-3.5 rounded-xl border border-rose-800/80 bg-rose-950/40 text-xs text-rose-300 flex items-center gap-2">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {disclaimer && (
        <div className="p-3 rounded-xl border border-slate-800/80 bg-slate-900/60 text-xs text-slate-400">
          ℹ️ {disclaimer} {routeIntelligence.length > 0 && `(Monitoring ${routeIntelligence.length} network corridors)`}
        </div>
      )}

      {feedback && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between transition-all ${
            feedback.type === 'success'
              ? 'bg-emerald-950/50 border-emerald-800/80 text-emerald-300'
              : 'bg-rose-950/50 border-rose-800/80 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2.5">
            <span className="font-bold">{feedback.type === 'success' ? '✓' : '✕'}</span>
            <span>{feedback.message}</span>
          </div>
          <button onClick={() => setFeedback(null)} className="text-xs opacity-60 hover:opacity-100">
            ✕
          </button>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* 2. Operational Environment Cards (Weather + Fleet Availability)       */}
      {/* --------------------------------------------------------------------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Card A: Weather-Aware Transit Operations (Phase 3) */}
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-md flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <span className="text-base">🌦️</span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Weather-Aware Operations
                </h3>
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                    weather?.condition === 'NORMAL'
                      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                      : weather?.condition === 'LIGHT_RAIN'
                      ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                      : weather?.condition === 'HEAVY_RAIN'
                      ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                      : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                  }`}
                >
                  {weather?.condition || 'CHECKING...'}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">
                  {weather?.is_live ? '• LIVE Open-Meteo' : '• SIMULATED DRILL'}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Coimbatore Temp</div>
                <div className="text-sm font-bold text-slate-200">
                  {weather ? `${weather.temperature_c}°C` : '29.0°C'}
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Precipitation</div>
                <div className="text-sm font-bold text-blue-400">
                  {weather ? `${weather.precipitation_mm} mm` : '0.0 mm'}
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Transfer Time Penalty</div>
                <div className="text-sm font-bold text-amber-400">
                  {weather ? `${weather.travel_time_multiplier}x` : '1.0x'}
                </div>
              </div>
            </div>

            <p className="text-[11px] text-slate-400 mt-2.5 bg-slate-950/40 p-2 rounded-lg border border-slate-800/50">
              {weather?.impact_summary || 'Operating under baseline Coimbatore transit parameters.'}
            </p>

            {!weather?.is_live && weather?.source === 'OFFLINE_FALLBACK' && (
              <div className="mt-2 text-[10px] text-amber-400/90 bg-amber-950/20 border border-amber-900/40 px-2 py-1 rounded flex items-center gap-1.5">
                <span>⚠️</span>
                <span>Live weather API unreachable; operating with deterministic offline physics baseline.</span>
              </div>
            )}
          </div>

          {/* Quick Scenario Toggles */}
          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-1 text-[11px]">
            <span className="text-slate-500 text-[10px]">Simulate Scenario:</span>
            <div className="flex flex-wrap items-center gap-1">
              <button
                onClick={() => handleApplyWeatherScenario('NORMAL')}
                disabled={isUpdatingWeather}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  weather?.condition === 'NORMAL' && !weather?.is_live
                    ? 'bg-emerald-500/30 text-emerald-300 border border-emerald-500/50'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                }`}
                title="Simulate clear, normal transit weather"
              >
                Normal
              </button>
              <button
                onClick={() => handleApplyWeatherScenario('LIGHT_RAIN')}
                disabled={isUpdatingWeather}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  weather?.condition === 'LIGHT_RAIN'
                    ? 'bg-blue-500/30 text-blue-300 border border-blue-500/50'
                    : 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-300'
                }`}
                title="Simulate light rain (-10% speed, +11% deadhead time)"
              >
                Light Rain
              </button>
              <button
                onClick={() => handleApplyWeatherScenario('HEAVY_RAIN')}
                disabled={isUpdatingWeather}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  weather?.condition === 'HEAVY_RAIN'
                    ? 'bg-amber-500/30 text-amber-300 border border-amber-500/50'
                    : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300'
                }`}
                title="Simulate heavy downpour (-25% speed, +33% deadhead time)"
              >
                Heavy Rain
              </button>
              <button
                onClick={() => handleApplyWeatherScenario('SEVERE_WEATHER')}
                disabled={isUpdatingWeather}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  weather?.condition === 'SEVERE_WEATHER'
                    ? 'bg-rose-500/30 text-rose-300 border border-rose-500/50'
                    : 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-300'
                }`}
                title="Simulate severe storm (-45% speed, +82% deadhead time)"
              >
                Severe Storm
              </button>
              <button
                onClick={() => handleApplyWeatherScenario('LIVE_RESET')}
                disabled={isUpdatingWeather}
                className={`px-2 py-0.5 rounded text-[10px] font-semibold transition-colors ${
                  weather?.is_live
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : 'bg-slate-800 hover:bg-slate-700 text-slate-400'
                }`}
                title="Reset to live Open-Meteo Coimbatore observation"
              >
                Live (Reset)
              </button>
            </div>
          </div>
        </div>

        {/* Card B: Breakdown Management & Fleet Availability (Phase 4) */}
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-md flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <span className="text-base">🔧</span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Fleet Availability & Breakdown Status
                </h3>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                  (breakdownSummary?.active_breakdowns || 0) === 0
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                }`}
              >
                {breakdownSummary?.active_breakdowns || 0} ACTIVE INCIDENTS
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Fleet Availability</div>
                <div className="text-sm font-bold text-emerald-400">
                  {breakdownSummary?.fleet_availability_pct ?? 100}%
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Under Repair</div>
                <div className="text-sm font-bold text-amber-400">
                  {breakdownSummary?.under_repair_count ?? 0}
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <div className="text-[10px] text-slate-500">Capacity Lost</div>
                <div className="text-sm font-bold text-rose-400">
                  {breakdownSummary?.total_capacity_lost ?? 0} seats
                </div>
              </div>
            </div>

            {/* Active Breakdowns List */}
            <div className="mt-2.5 space-y-1.5 max-h-24 overflow-y-auto pr-1">
              {breakdownSummary && breakdownSummary.incidents.length > 0 ? (
                breakdownSummary.incidents.map((inc) => (
                  <div
                    key={inc.id}
                    className="p-1.5 rounded-lg bg-slate-950/80 border border-rose-900/50 flex items-center justify-between text-[11px]"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-rose-400">Bus {inc.bus_number}</span>
                      <span className="text-slate-400 text-[10px]">
                        Route {inc.route_number || 'UNKNOWN'}
                      </span>
                      <span className="text-slate-500 text-[10px] hidden sm:inline">
                        ({inc.location_name})
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[9px]">
                        {inc.status}
                      </span>
                      {inc.status === 'REPORTED' && (
                        <button
                          onClick={() => handleUpdateBreakdownLifecycle(inc.id, 'CONFIRMED', inc.bus_number)}
                          className="px-1.5 py-0.5 text-[9px] bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 rounded font-bold"
                          title="Advance to CONFIRMED"
                        >
                          Confirm
                        </button>
                      )}
                      {inc.status !== 'UNDER_REPAIR' && (
                        <button
                          onClick={() => handleUpdateBreakdownLifecycle(inc.id, 'UNDER_REPAIR', inc.bus_number)}
                          className="px-1.5 py-0.5 text-[9px] bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 rounded"
                          title="Advance to UNDER_REPAIR"
                        >
                          Repair
                        </button>
                      )}
                      <button
                        onClick={() => handleUpdateBreakdownLifecycle(inc.id, 'AVAILABLE', inc.bus_number)}
                        className="px-1.5 py-0.5 text-[9px] bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 rounded font-bold"
                        title="Mark REPAIRED & Restore to Service"
                      >
                        Recover
                      </button>
                      <button
                        onClick={() => handleInspectReplacement(inc.bus_id)}
                        disabled={isLoadingReplacement}
                        className="px-1.5 py-0.5 text-[9px] bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 rounded disabled:opacity-50"
                        title="Evaluate replacement donor bus"
                      >
                        {isLoadingReplacement ? 'Evaluating...' : 'Find Replacement'}
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-2 text-center text-[11px] text-slate-500 bg-slate-950/30 rounded-lg">
                  All 12 buses operational. Zero mechanical breakdowns reported.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* --------------------------------------------------------------------- */}
      {/* 3. Before-and-After Optimization Impact Analysis (Phase 6)            */}
      {/* --------------------------------------------------------------------- */}
      {optimizationPlan && (
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 shadow-md">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base">📊</span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Predicted Optimization Impact & Before/After Analysis
                </h3>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-500/15 text-indigo-400 border border-indigo-500/30">
                  {optimizationPlan.solver_status} ({optimizationPlan.solver_time_ms}ms)
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5 font-mono">
                Plan ID: {optimizationPlan.plan_id} • Weather: {optimizationPlan.weather_condition} ({optimizationPlan.weather_delay_factor}x)
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Net Plan Utility:</span>
              <span className="text-sm font-bold text-emerald-400 font-mono">
                {optimizationPlan.objective_value ?? 0} pts
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3">
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Overloaded Routes</div>
              <div className="text-sm font-extrabold text-white mt-0.5 flex items-center justify-center gap-1.5">
                <span className="text-rose-400">{optimizationPlan.baseline_metrics.overloaded_routes_count}</span>
                <span className="text-slate-600">→</span>
                <span className="text-emerald-400">{optimizationPlan.predicted_metrics.overloaded_routes_count}</span>
              </div>
              <div className="text-[9px] text-emerald-400 mt-0.5">
                {optimizationPlan.predicted_improvement_pct}% reduction
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Unmet Demand Proxy</div>
              <div className="text-sm font-extrabold text-white mt-0.5 flex items-center justify-center gap-1.5">
                <span className="text-rose-400">{optimizationPlan.baseline_metrics.total_unmet_demand_proxy}</span>
                <span className="text-slate-600">→</span>
                <span className="text-emerald-400">{optimizationPlan.predicted_metrics.total_unmet_demand_proxy}</span>
              </div>
              <div className="text-[9px] text-slate-400 mt-0.5">pax over comfortable load</div>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Capacity Transferred</div>
              <div className="text-sm font-extrabold text-purple-400 mt-0.5">
                {optimizationPlan.capacity_reallocated_seats} seats
              </div>
              <div className="text-[9px] text-slate-400 mt-0.5">
                Across {optimizationPlan.total_allocations_count} reallocations
              </div>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Deadhead Distance</div>
              <div className="text-sm font-extrabold text-blue-400 mt-0.5">
                {optimizationPlan.total_transfer_distance_km} km
              </div>
              <div className="text-[9px] text-slate-400 mt-0.5">Network deadhead budget</div>
            </div>

            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-center">
              <div className="text-[10px] text-slate-500 uppercase">Est. Transfer Time</div>
              <div className="text-sm font-extrabold text-amber-400 mt-0.5">
                {optimizationPlan.total_transfer_time_min} min
              </div>
              <div className="text-[9px] text-amber-500/80 mt-0.5">
                Weather-adjusted ({optimizationPlan.weather_delay_factor}x)
              </div>
            </div>
          </div>

          {/* Binding Constraints Disclosures */}
          {optimizationPlan.binding_constraints.length > 0 && (
            <div className="mt-3 p-2.5 rounded-lg bg-amber-950/20 border border-amber-900/40 text-[11px] text-amber-300 space-y-0.5">
              <div className="font-bold flex items-center gap-1.5">
                <span>⚠️</span> Active Mathematical Optimization Constraints:
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-amber-200/90 pl-1">
                {optimizationPlan.binding_constraints.map((bc, idx) => (
                  <li key={idx}>{bc}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* 4. Resilience Scenario Evaluation Sandbox (Phase 5)                   */}
      {/* --------------------------------------------------------------------- */}
      {showSandbox && (
        <div className="p-5 rounded-2xl bg-gradient-to-br from-purple-950/30 via-slate-900 to-slate-950 border border-purple-800/60 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-purple-800/40">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base">🧪</span>
                <h3 className="text-sm font-extrabold text-purple-300 uppercase tracking-wider">
                  Isolated Resilience Scenario Evaluation Sandbox
                </h3>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-200 font-mono">
                  Phase 5 Non-Mutating Sandbox
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Simulate simultaneous high demand spikes, vehicle breakdowns, and weather disruption to measure network resilience without modifying production telemetry.
              </p>
            </div>
            <button
              onClick={() => setShowSandbox(false)}
              className="text-slate-400 hover:text-white text-xs px-2 py-1 bg-slate-800 rounded"
            >
              ✕ Close
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <label className="text-slate-400 block mb-1">Route 101 Demand Drill:</label>
              <select
                value={sandboxDemand101}
                onChange={(e) => setSandboxDemand101(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
              >
                <option value="NORMAL">NORMAL (60% load)</option>
                <option value="HIGH">HIGH (95% load surge)</option>
                <option value="LOW">LOW (35% load)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Route 404 Demand Drill:</label>
              <select
                value={sandboxDemand404}
                onChange={(e) => setSandboxDemand404(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
              >
                <option value="NORMAL">NORMAL (60% load)</option>
                <option value="HIGH">HIGH (95% load surge)</option>
                <option value="LOW">LOW (35% load)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Simulated Breakdown Bus:</label>
              <select
                value={sandboxBreakdownBus}
                onChange={(e) => setSandboxBreakdownBus(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
              >
                <option value="">None (All Available)</option>
                <option value="101A">Bus 101A (Route 101)</option>
                <option value="303B">Bus 303B (Route 303)</option>
                <option value="404A">Bus 404A (Route 404)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-400 block mb-1">Simulated Weather:</label>
              <select
                value={sandboxWeather}
                onChange={(e) => setSandboxWeather(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
              >
                <option value="NORMAL">NORMAL (Fair weather)</option>
                <option value="LIGHT_RAIN">LIGHT_RAIN (-10% speed)</option>
                <option value="HEAVY_RAIN">HEAVY_RAIN (-25% speed, +33% time)</option>
                <option value="SEVERE_WEATHER">SEVERE_WEATHER (-45% speed, +82% time)</option>
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-[11px] text-purple-300 font-mono">
              Evaluates CP-SAT buffering capacity, minimum coverage retention, and load absorption.
            </span>
            <button
              onClick={handleRunSandboxEvaluation}
              disabled={isEvaluatingSandbox}
              className="px-4 py-2 text-xs font-bold text-white bg-purple-600 hover:bg-purple-500 rounded-lg transition-colors flex items-center gap-1.5"
            >
              <span>{isEvaluatingSandbox ? 'Simulating...' : '⚡ Evaluate Resilience Drill'}</span>
            </button>
          </div>

          {/* Sandbox Results */}
          {sandboxResult && (
            <div className="p-3.5 rounded-xl bg-slate-950/90 border border-purple-800/80 text-xs space-y-2 mt-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white uppercase">{sandboxResult.scenario_name}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      sandboxResult.resilience_rating === 'HIGH RESILIENCE'
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : sandboxResult.resilience_rating === 'MODERATE RESILIENCE'
                        ? 'bg-amber-500/20 text-amber-300'
                        : 'bg-rose-500/20 text-rose-300'
                    }`}
                  >
                    {sandboxResult.resilience_rating}
                  </span>
                </div>
                <div className="text-sm font-mono font-bold text-purple-300">
                  Resilience Score: {sandboxResult.resilience_score} / 100
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-center">
                <div className="p-2 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">Overloaded Corridors</div>
                  <div className="text-sm font-bold text-rose-400">
                    {sandboxResult.scenario_metrics.overloaded_routes_count} / 6
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">Fleet Available</div>
                  <div className="text-sm font-bold text-emerald-400">
                    {sandboxResult.scenario_metrics.operational_buses_count} buses
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">Total Unmet Demand</div>
                  <div className="text-sm font-bold text-amber-400">
                    {sandboxResult.scenario_metrics.total_unmet_demand_proxy} pax
                  </div>
                </div>
                <div className="p-2 rounded bg-slate-900 border border-slate-800">
                  <div className="text-[10px] text-slate-500">Routes Below Coverage</div>
                  <div className="text-sm font-bold text-slate-300">
                    {sandboxResult.scenario_metrics.routes_below_minimum_coverage}
                  </div>
                </div>
              </div>

              <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5 pt-1">
                {sandboxResult.key_findings.map((kf, idx) => (
                  <li key={idx}>{kf}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* 5. Feasible Reassignment Proposals & Dispatcher Decision Controls     */}
      {/* --------------------------------------------------------------------- */}
      <div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span>📋</span> Feasible Reassignment Proposals & Dispatcher Approvals
            </h3>
            <p className="text-xs text-slate-400">
              Review individual candidate proposals. Operational approval authorizes the recommendation; explicit execution triggers real-world transfer.
            </p>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-lg">
              <span className="text-[11px] text-slate-500 px-1 hidden md:inline">Priority:</span>
              {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setFilterPriority(p)}
                  className={`px-2 py-0.5 text-xs font-semibold rounded transition-colors ${
                    filterPriority === p ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-lg">
              <span className="text-[11px] text-slate-500 px-1 hidden md:inline">Review:</span>
              {(['ALL', 'PENDING', 'APPROVED', 'REJECTED', 'DEFERRED'] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setFilterDecision(d)}
                  className={`px-2 py-0.5 text-xs font-semibold rounded transition-colors ${
                    filterDecision === d ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {d === 'ALL' ? 'All' : d}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Diagnostic reason notices */}
        {diagnosticReasons.length > 0 && (
          <div className="mb-4 space-y-2">
            {diagnosticReasons.map((reason, idx) => (
              <div
                key={idx}
                className="bg-slate-900/80 border border-amber-900/50 rounded-xl p-3 text-xs text-slate-300 flex items-start gap-2.5"
              >
                <span className="text-amber-400 mt-0.5">ℹ️</span>
                <span>{reason}</span>
              </div>
            ))}
          </div>
        )}

        {/* Recommendations Grid */}
        {isLoading ? (
          <div className="p-8 text-center text-xs text-slate-400 bg-slate-900 rounded-xl border border-slate-800">
            Evaluating transit network imbalances and computing CP-SAT optimization...
          </div>
        ) : filteredRecommendations.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredRecommendations.map((rec) => {
              const isApproved = (rec.review_status || '').toUpperCase() === 'APPROVED';
              const isExecuted = (rec.execution_status || '').toUpperCase() === 'EXECUTED';

              return (
                <div
                  key={rec.id}
                  className={`p-4 rounded-xl border transition-all ${
                    isExecuted
                      ? 'bg-purple-950/20 border-purple-800/80 shadow-lg'
                      : isApproved
                      ? 'bg-emerald-950/20 border-emerald-800/80'
                      : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Card Header: IDs, Badges, Score */}
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-xs text-blue-400">
                        {rec.source_route_number} → {rec.target_route_number}
                      </span>
                      <StatusBadge status={rec.priority} type="priority" size="sm" />
                      {isExecuted ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                          ⚡ EXECUTED
                        </span>
                      ) : (
                        <StatusBadge status={rec.review_status || 'PENDING'} type="review" size="sm" />
                      )}
                    </div>
                    <div className="text-right">
                      <span className="text-xs font-mono font-bold text-emerald-400">
                        {rec.score} pts
                      </span>
                    </div>
                  </div>

                  {/* Body Content */}
                  <div className="py-2.5 space-y-2 text-xs">
                    <p className="text-slate-300 text-[11px] leading-relaxed">{rec.reason}</p>

                    <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
                      <div>
                        <span className="text-slate-500">Candidate Bus: </span>
                        <strong className="text-slate-200">
                          {rec.candidate_bus_number || 'None'}
                        </strong>
                        <span className="text-slate-400 text-[10px]">
                          {' '}
                          ({rec.available_capacity ?? 0} seats free)
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Deadhead Distance: </span>
                        <strong className="text-slate-200">
                          {rec.distance_meters !== null && rec.distance_meters !== undefined
                            ? `${(rec.distance_meters / 1000).toFixed(1)} km`
                            : 'N/A'}
                        </strong>
                        <span className="text-slate-400 text-[10px]">
                          {' '}
                          ({rec.estimated_travel_time_minutes ?? 0}m)
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Target Load: </span>
                        <span className="text-rose-400 font-bold">
                          {Math.round(rec.target_route_load_factor * 100)}%
                        </span>
                        {rec.projected_target_load_factor !== null && (
                          <span className="text-emerald-400 font-bold">
                            {' '}
                            → {Math.round(rec.projected_target_load_factor * 100)}%
                          </span>
                        )}
                      </div>
                      <div>
                        <span className="text-slate-500">Source Load: </span>
                        <span className="text-blue-400 font-bold">
                          {Math.round(rec.source_route_load_factor * 100)}%
                        </span>
                      </div>
                    </div>

                    {rec.limitations.length > 0 && (
                      <div className="text-[10px] text-amber-300/90 bg-amber-950/20 p-1.5 rounded border border-amber-900/30 space-y-0.5">
                        {rec.limitations.map((lim, lIdx) => (
                          <div key={lIdx}>• {lim}</div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions Bar */}
                  <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2">
                    <button
                      onClick={() => handleViewHistory(rec.id)}
                      className="text-[11px] text-slate-400 hover:text-white flex items-center gap-1 transition-colors"
                    >
                      <span>📜</span> Audit History
                    </button>

                    <div className="flex items-center gap-1.5">
                      {!isApproved && !isExecuted && (
                        <>
                          <button
                            onClick={() => handleOpenReview(rec, 'APPROVED')}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/30 transition-colors"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => handleOpenReview(rec, 'DEFERRED')}
                            className="px-2 py-1 text-xs rounded bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                          >
                            Defer
                          </button>
                          <button
                            onClick={() => handleOpenReview(rec, 'REJECTED')}
                            className="px-2 py-1 text-xs rounded bg-rose-600/20 text-rose-300 hover:bg-rose-600/30 border border-rose-500/30 transition-colors"
                          >
                            Reject
                          </button>
                        </>
                      )}

                      {isApproved && !isExecuted && (
                        <button
                          onClick={() => handleOpenExecute(rec)}
                          className="px-3 py-1 text-xs font-bold rounded bg-purple-600 hover:bg-purple-500 text-white shadow-md shadow-purple-900/50 transition-colors flex items-center gap-1"
                        >
                          <span>⚡</span> Execute Transfer
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-8 text-center text-xs text-slate-400 bg-slate-900 rounded-xl border border-slate-800">
            No reallocation recommendations matching active filters.
          </div>
        )}
      </div>

      {/* --------------------------------------------------------------------- */}
      {/* 6. Modals (Review, Execute, Report Breakdown, Replacement Planner)   */}
      {/* --------------------------------------------------------------------- */}

      {/* Review Modal */}
      {activeReviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white">Record Dispatcher Review</h3>
              <button
                onClick={() => setActiveReviewModal(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="text-xs space-y-3">
              <p className="text-slate-300">
                Decision: <strong className="text-blue-400">{activeReviewModal.decision}</strong> for{' '}
                <span className="font-mono">{activeReviewModal.recNumber}</span>
              </p>
              <div>
                <label className="text-slate-400 block mb-1">Dispatcher Identity:</label>
                <input
                  type="text"
                  value={dispatcherId}
                  onChange={(e) => setDispatcherId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
                />
              </div>
              <div>
                <label className="text-slate-400 block mb-1">Operational Justification / Notes:</label>
                <textarea
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. Authorized capacity reallocation due to high passenger congestion"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setActiveReviewModal(null)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white rounded"
              >
                Cancel
              </button>
              <button
                disabled={isSubmitting}
                onClick={handleConfirmReview}
                className="px-4 py-1.5 text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 rounded-lg disabled:opacity-50"
              >
                {isSubmitting ? 'Recording...' : 'Submit Decision'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Execution Modal */}
      {activeExecutionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="max-w-md w-full bg-slate-900 border border-purple-800/80 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>⚡</span> Execute Live Fleet Reassignment
              </h3>
              <button
                onClick={() => setActiveExecutionModal(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="text-xs space-y-3">
              <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div>
                  Bus: <strong className="text-purple-300 font-mono">Bus {activeExecutionModal.candidate_bus_number}</strong>
                </div>
                <div>
                  Transfer Corridor: <strong>Route {activeExecutionModal.source_route_number} → Route {activeExecutionModal.target_route_number}</strong>
                </div>
                <div>
                  Deadhead Distance: <strong>{activeExecutionModal.distance_meters ? (activeExecutionModal.distance_meters / 1000).toFixed(1) : '2.5'} km</strong>
                </div>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Execution Dispatcher ID:</label>
                <input
                  type="text"
                  value={executingDispatcherId}
                  onChange={(e) => setExecutingDispatcherId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Execution Remarks:</label>
                <textarea
                  rows={2}
                  value={executionNotes}
                  onChange={(e) => setExecutionNotes(e.target.value)}
                  placeholder="e.g. Authorized live fleet reallocation to relieve peak congestion"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white resize-none"
                />
              </div>

              {executionModalError && (
                <div className="p-2.5 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-200 text-xs flex items-start gap-2">
                  <span className="text-rose-400 font-bold text-sm">⚠️</span>
                  <div>
                    <div className="font-semibold text-rose-300">Reassignment Blocked</div>
                    <div className="mt-0.5 text-[11px] leading-relaxed">{executionModalError}</div>
                  </div>
                </div>
              )}

              <div className="p-2 rounded bg-purple-950/40 border border-purple-800/60 text-[11px] text-purple-200">
                Immediately updates <strong>buses.route_id</strong> and signals runtime simulator to continuous deadheading.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setActiveExecutionModal(null)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white rounded"
              >
                Cancel
              </button>
              <button
                disabled={isExecuting}
                onClick={handleConfirmExecute}
                className="px-4 py-1.5 text-xs font-bold text-white bg-purple-600 hover:bg-purple-500 rounded-lg disabled:opacity-50"
              >
                {isExecuting ? 'Executing...' : '⚡ Confirm & Dispatch Vehicle'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Report Breakdown Modal (Phase 4) */}
      {showBreakdownModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="max-w-md w-full bg-slate-900 border border-rose-800/80 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>🚨</span> Report Vehicle Breakdown
              </h3>
              <button
                onClick={() => setShowBreakdownModal(false)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="text-xs space-y-3">
              <div>
                <label className="text-slate-400 block mb-1">Select Broken Bus:</label>
                <select
                  value={reportBusNumber}
                  onChange={(e) => setReportBusNumber(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white font-mono"
                >
                  <option value="101A">Bus 101A (Route 101)</option>
                  <option value="101B">Bus 101B (Route 101)</option>
                  <option value="202A">Bus 202A (Route 202)</option>
                  <option value="202B">Bus 202B (Route 202)</option>
                  <option value="303A">Bus 303A (Route 303)</option>
                  <option value="303B">Bus 303B (Route 303)</option>
                  <option value="404A">Bus 404A (Route 404)</option>
                  <option value="404B">Bus 404B (Route 404)</option>
                  <option value="505A">Bus 505A (Route 505)</option>
                  <option value="505B">Bus 505B (Route 505)</option>
                  <option value="606A">Bus 606A (Route 606)</option>
                  <option value="606B">Bus 606B (Route 606)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Breakdown Reason:</label>
                <select
                  value={reportReason}
                  onChange={(e) => setReportReason(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
                >
                  <option value="Engine failure">Engine failure</option>
                  <option value="Mechanical failure">Mechanical failure</option>
                  <option value="Electrical failure">Electrical failure</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Location or Stop Name:</label>
                <input
                  type="text"
                  value={reportLocation}
                  onChange={(e) => setReportLocation(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Severity Tier:</label>
                <select
                  value={reportSeverity}
                  onChange={(e) => setReportSeverity(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white"
                >
                  <option value="HIGH">HIGH (Corridor capacity reduced)</option>
                  <option value="CRITICAL">CRITICAL (Service halted)</option>
                  <option value="MEDIUM">MEDIUM (Minor mechanical issue)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Fault Description / Driver Notes:</label>
                <textarea
                  rows={2}
                  value={reportNotes}
                  onChange={(e) => setReportNotes(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-white resize-none"
                />
              </div>

              <div className="p-2 rounded bg-rose-950/40 border border-rose-800/60 text-[11px] text-rose-200">
                Immediately updates bus status to <strong>BROKEN_DOWN</strong> and halts movement in the live simulator.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setShowBreakdownModal(false)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:text-white rounded"
              >
                Cancel
              </button>
              <button
                disabled={isReportingBreakdown}
                onClick={handleReportBreakdown}
                className="px-4 py-1.5 text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 rounded-lg disabled:opacity-50"
              >
                {isReportingBreakdown ? 'Reporting...' : 'Confirm Breakdown'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Replacement Candidate Modal (Phase 4) */}
      {replacementModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="max-w-lg w-full bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <span>🔄</span> Replacement Bus Planning: Bus {replacementModal.broken_bus_number}
              </h3>
              <button onClick={() => setReplacementModal(null)} className="text-slate-400 hover:text-white text-xs">
                ✕
              </button>
            </div>

            <div className="text-xs space-y-3">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1">
                <div>
                  Affected Route: <strong className="text-rose-400">Route {replacementModal.route_number}</strong>
                </div>
                <div>
                  Lost Capacity: <strong>{replacementModal.capacity_lost} seats</strong>
                </div>
                <div className="text-slate-300 mt-1">{replacementModal.explanation}</div>
              </div>

              <div>
                <h4 className="font-bold text-slate-300 mb-1">Eligible Donor Corridors:</h4>
                {replacementModal.eligible_donor_routes.length > 0 ? (
                  <div className="space-y-1">
                    {replacementModal.eligible_donor_routes.map((dr) => (
                      <div
                        key={dr.route_id}
                        className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between"
                      >
                        <span className="font-mono font-bold text-slate-200">
                          Route {dr.route_number} ({dr.name || 'Corridor'})
                        </span>
                        <span className="text-emerald-400">{Math.round(dr.load_factor * 100)}% load</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-slate-500 text-[11px] p-2 bg-slate-950 rounded">
                    No donor routes with spare capacity.
                  </div>
                )}
              </div>

              {replacementModal.binding_constraints.length > 0 && (
                <div className="p-2 rounded bg-amber-950/20 border border-amber-900/40 text-[10px] text-amber-300 space-y-0.5">
                  <div className="font-bold">Active Constraints:</div>
                  {replacementModal.binding_constraints.map((bc, idx) => (
                    <div key={idx}>• {bc}</div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-2 border-t border-slate-800 text-right">
              <button
                onClick={() => setReplacementModal(null)}
                className="px-3 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Audit History Drawer */}
      {activeHistoryRecId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="max-w-xl w-full bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-base font-bold text-white">Decision & Execution Audit Trail</h3>
                <p className="text-xs text-slate-400 font-mono">{activeHistoryRecId}</p>
              </div>
              <button
                onClick={() => setActiveHistoryRecId(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 pr-1 text-xs">
              {isLoadingHistory ? (
                <div className="py-8 text-center text-slate-400">Loading audit history...</div>
              ) : (
                <>
                  <div>
                    <h4 className="text-xs font-bold text-purple-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <span>⚡</span>
                      <span>Reassignment Executions ({historyExecutionRecords.length})</span>
                    </h4>
                    {historyExecutionRecords.length > 0 ? (
                      historyExecutionRecords.map((item) => (
                        <div
                          key={item.id}
                          className="p-3 rounded-lg bg-purple-950/20 border border-purple-800/60 space-y-1.5 mb-2"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-white">Bus {item.bus_number}</span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              {new Date(item.created_at).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Route {item.source_route_number} → Route {item.target_route_number} (by {item.dispatcher_id})
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-500">
                        No executions recorded.
                      </div>
                    )}
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-blue-300 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                      <span>📋</span>
                      <span>Dispatcher Review Decisions ({historyRecords.length})</span>
                    </h4>
                    {historyRecords.length > 0 ? (
                      historyRecords.map((item) => (
                        <div
                          key={item.id}
                          className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-1.5 mb-2"
                        >
                          <div className="flex items-center justify-between">
                            <StatusBadge status={item.decision} type="review" size="sm" />
                            <span className="text-[10px] text-slate-500 font-mono">
                              {new Date(item.created_at).toLocaleString()}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Dispatcher: {item.dispatcher_id || 'DISPATCHER-1'}
                          </div>
                          {item.notes && <p className="text-slate-300 bg-slate-900/60 p-2 rounded">"{item.notes}"</p>}
                        </div>
                      ))
                    ) : (
                      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-slate-500">
                        No review decisions recorded.
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="pt-2 border-t border-slate-800 text-right">
              <button
                onClick={() => setActiveHistoryRecId(null)}
                className="px-3 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
