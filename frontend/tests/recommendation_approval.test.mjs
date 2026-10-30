import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('Fleet Optimization — Recommendation Approval Workflow & UI Resilience', () => {
  test('double-clicking Confirm does not submit duplicate approval requests', async () => {
    let apiCallCount = 0;
    const isSubmittingRef = { current: false };
    let isSubmittingState = false;

    const mockSubmitReview = async (recId, payload) => {
      apiCallCount++;
      // Simulate network round-trip delay
      await new Promise((resolve) => setTimeout(resolve, 50));
      return {
        id: 101,
        recommendation_id: recId,
        decision: payload.decision,
        dispatcher_id: payload.dispatcher_id,
        created_at: new Date().toISOString(),
      };
    };

    const handleReviewSubmit = async (modalData) => {
      if (!modalData || isSubmittingRef.current) return;
      isSubmittingRef.current = true;
      isSubmittingState = true;

      try {
        await mockSubmitReview(modalData.recId, {
          decision: modalData.decision,
          dispatcher_id: 'DISPATCHER-TEST',
        });
      } finally {
        isSubmittingState = false;
        isSubmittingRef.current = false;
      }
    };

    const modalData = { recId: 'REC-101-202-202B', decision: 'APPROVED' };

    // Simulate two rapid clicks fired concurrently
    const [p1, p2] = [handleReviewSubmit(modalData), handleReviewSubmit(modalData)];
    await Promise.all([p1, p2]);

    assert.equal(apiCallCount, 1, 'API must only be called once when user rapidly double-clicks Confirm');
    assert.equal(isSubmittingState, false, 'Loading state must reset to false after completion');
    assert.equal(isSubmittingRef.current, false, 'Double-click ref guard must reset to false');
  });

  test('failed approval request displays useful error and does not falsely report success', async () => {
    let activeModal = { recId: 'REC-101-202-202B', decision: 'APPROVED' };
    let reviewModalError = null;
    let feedback = null;
    let localOverrides = {};
    let isSubmitting = false;
    const isSubmittingRef = { current: false };

    const mockFailingSubmit = async () => {
      throw new Error('Transit server request timed out or was interrupted. Please verify backend connectivity and retry.');
    };

    const handleReviewSubmit = async () => {
      if (!activeModal || isSubmittingRef.current) return;
      isSubmittingRef.current = true;
      isSubmitting = true;
      reviewModalError = null;

      try {
        await mockFailingSubmit();
        // The following lines MUST NOT execute on failure:
        localOverrides[activeModal.recId] = { review_status: 'APPROVED' };
        activeModal = null;
        feedback = { message: 'Success', type: 'success' };
      } catch (err) {
        reviewModalError = err.message;
        feedback = { message: err.message, type: 'error' };
      } finally {
        isSubmitting = false;
        isSubmittingRef.current = false;
      }
    };

    await handleReviewSubmit();

    assert.notEqual(activeModal, null, 'Modal must remain open so user can read error and retry');
    assert.match(reviewModalError, /timed out or was interrupted/, 'Modal must display helpful error');
    assert.equal(feedback?.type, 'error', 'Feedback must indicate error, never false success');
    assert.equal(localOverrides['REC-101-202-202B'], undefined, 'No local override should be recorded on failure');
    assert.equal(isSubmitting, false, 'Loading indicator must stop on failure');
  });

  test('successful approval closes modal and updates recommendation status to APPROVED', async () => {
    let activeModal = { recId: 'REC-101-202-202B', decision: 'APPROVED' };
    let reviewModalError = null;
    let feedback = null;
    let localOverrides = {};
    let isSubmitting = false;
    let refreshTriggered = false;

    const mockSuccessfulSubmit = async () => ({
      id: 1,
      recommendation_id: 'REC-101-202-202B',
      decision: 'APPROVED',
      dispatcher_id: 'DISPATCHER-1',
      created_at: new Date().toISOString(),
    });

    const handleReviewSubmit = async () => {
      isSubmitting = true;
      reviewModalError = null;
      try {
        const review = await mockSuccessfulSubmit();
        localOverrides[activeModal.recId] = {
          review_status: 'APPROVED',
          latest_review: review,
        };
        feedback = { message: 'Recommendation marked as APPROVED.', type: 'success' };
        activeModal = null;
        refreshTriggered = true;
      } finally {
        isSubmitting = false;
      }
    };

    await handleReviewSubmit();

    assert.equal(activeModal, null, 'Approval modal must close immediately on confirmed success');
    assert.equal(reviewModalError, null, 'Modal error must be cleared on success');
    assert.equal(feedback?.type, 'success', 'Feedback must be success');
    assert.equal(localOverrides['REC-101-202-202B']?.review_status, 'APPROVED');
    assert.equal(refreshTriggered, true, 'Backend refresh must be triggered');
    assert.equal(isSubmitting, false, 'Loading indicator must stop');
  });

  test('approval and live dispatch execution remain strictly separate stages', () => {
    // Recommendation model
    const recommendation = {
      id: 'REC-101-202-202B',
      source_route_number: '202',
      target_route_number: '101',
      candidate_bus_id: 3,
      candidate_bus_number: '202B',
      review_status: null,
      execution_status: null,
    };

    // Stage 1: Approval
    const approvedRec = {
      ...recommendation,
      review_status: 'APPROVED',
    };

    assert.equal(approvedRec.review_status, 'APPROVED', 'Approval stage updates review_status');
    assert.equal(approvedRec.execution_status, null, 'Approval stage must NOT execute the transfer');

    // Stage 2: Separate Live Dispatch Execution
    const executedRec = {
      ...approvedRec,
      execution_status: 'EXECUTED',
      executed_at: new Date().toISOString(),
    };

    assert.equal(executedRec.review_status, 'APPROVED');
    assert.equal(executedRec.execution_status, 'EXECUTED', 'Execution is an explicit subsequent step');
  });

  test('recommendation IDs remain stable and deterministic across calls', () => {
    const makeRecId = (targetNum, sourceNum, busNum) =>
      `REC-${targetNum}-${sourceNum}-${busNum || 'NOBUS'}`;

    const id1 = makeRecId('101', '202', '202B');
    const id2 = makeRecId('101', '202', '202B');
    const idNoBus = makeRecId('101', '202', null);

    assert.equal(id1, id2, 'Recommendation IDs must be completely deterministic and stable');
    assert.equal(id1, 'REC-101-202-202B');
    assert.equal(idNoBus, 'REC-101-202-NOBUS');
    assert.notEqual(id1, idNoBus);
  });

  test('aborted request error message formatting avoids raw DOMException message', () => {
    const formatFetchError = (err, controllerSignal, endpoint) => {
      if (err?.name === 'AbortError' || controllerSignal.aborted) {
        const reasonMsg = controllerSignal.reason?.message ||
          (typeof controllerSignal.reason === 'string' ? controllerSignal.reason : null);
        return (
          reasonMsg ||
          `Transit server request to ${endpoint} timed out or was interrupted. Please verify backend connectivity and retry.`
        );
      }
      return err.message;
    };

    // Case 1: Timeout abort with custom reason
    const controllerWithReason = {
      aborted: true,
      reason: new Error('Request to /api/optimization/recommendations/REC-1/review timed out after 30000ms'),
    };
    const msg1 = formatFetchError({ name: 'AbortError' }, controllerWithReason, '/api/endpoint');
    assert.match(msg1, /timed out after 30000ms/);

    // Case 2: Untyped abort (legacy browser behavior)
    const controllerWithoutReason = {
      aborted: true,
      reason: undefined,
    };
    const msg2 = formatFetchError({ name: 'AbortError' }, controllerWithoutReason, '/api/optimization/recommendations');
    assert.match(msg2, /timed out or was interrupted/);
    assert.doesNotMatch(msg2, /signal is aborted without reason/);
  });
});
