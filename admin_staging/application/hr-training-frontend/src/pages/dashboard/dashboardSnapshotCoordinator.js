export const isDashboardSnapshotExpired = (error) =>
  error?.response?.status === 409 &&
  error?.response?.data?.code === 'DASHBOARD_SNAPSHOT_EXPIRED';

const cancelled = () => Object.assign(new Error('Dashboard request superseded'), { name: 'AbortError' });
const filterKey = (filters) => JSON.stringify(filters);

export const createDashboardSnapshotCoordinator = ({ api, onCommit, onBusy, onError }) => {
  let generation = 0;
  let active = null;
  const recoveredAttention = new Set();

  const rememberAttention = (key) => {
    recoveredAttention.add(key);
    if (recoveredAttention.size > 20) {
      recoveredAttention.delete(recoveredAttention.values().next().value);
    }
  };

  const fetchPair = async (filters, signal, isCurrent, allowRecovery) => {
    for (let attempt = 0; attempt <= (allowRecovery ? 1 : 0); attempt += 1) {
      const kpi = await api.getManagementKpis(filters, { signal });
      if (!isCurrent()) throw cancelled();
      const snapshotId = kpi?.data?.snapshot?.snapshot_id;
      let summary;
      try {
        summary = await api.getManagementSummary(
          snapshotId ? { ...filters, snapshot_id: snapshotId } : filters,
          { signal }
        );
      } catch (error) {
        if (attempt === 0 && allowRecovery && isDashboardSnapshotExpired(error) && isCurrent()) {
          continue;
        }
        throw error;
      }
      if (!isCurrent()) throw cancelled();
      if (snapshotId && summary?.data?.snapshot?.snapshot_id !== snapshotId) {
        throw new Error('Dashboard snapshot versions do not match');
      }
      return summary?.data;
    }
    throw new Error('Dashboard snapshot recovery failed');
  };

  const load = (filters, { joinExisting = false, allowRecovery = true } = {}) => {
    const key = filterKey(filters);
    if (joinExisting && active?.key === key && !active.controller.signal.aborted) {
      return active.promise;
    }
    generation += 1;
    active?.controller.abort();
    const requestGeneration = generation;
    const controller = new AbortController();
    const isCurrent = () => generation === requestGeneration && !controller.signal.aborted;
    onBusy(true);
    onError(null);
    const promise = (async () => {
      const data = await fetchPair(filters, controller.signal, isCurrent, allowRecovery);
      if (!isCurrent()) throw cancelled();
      onCommit(data);
      return data;
    })();
    const record = { key, controller, promise };
    active = record;
    promise.then(
      () => {
        if (isCurrent()) onBusy(false);
        if (active === record) active = null;
      },
      (error) => {
        if (isCurrent()) {
          onError(error);
          onBusy(false);
        }
        if (active === record) active = null;
      }
    );
    return promise;
  };

  const loadAttention = async (kind, filters, snapshotId, interactionId, signal) => {
    if (signal?.aborted) throw cancelled();
    const context = (id) => JSON.stringify([kind, filterKey(filters), interactionId, id]);
    try {
      return await api.getManagementAttention(
        kind, snapshotId ? { ...filters, snapshot_id: snapshotId } : filters, { signal }
      );
    } catch (error) {
      const oldContext = context(snapshotId);
      if (!isDashboardSnapshotExpired(error) || recoveredAttention.has(oldContext) || signal?.aborted) {
        throw error;
      }
      rememberAttention(oldContext);
      const data = await load(filters, { joinExisting: true, allowRecovery: false });
      const replacementId = data?.snapshot?.snapshot_id;
      if (!replacementId) throw new Error('Dashboard recovery returned no snapshot ID');
      rememberAttention(context(replacementId));
      if (signal?.aborted) throw cancelled();
      return api.getManagementAttention(
        kind, { ...filters, snapshot_id: replacementId }, { signal }
      );
    }
  };

  const cancel = () => {
    generation += 1;
    active?.controller.abort();
    active = null;
  };

  return { load, loadAttention, cancel };
};
