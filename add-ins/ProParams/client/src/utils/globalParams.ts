import { useCallback, useEffect, useState } from 'react';

import { useToast } from '../components/common/Toast';
import { onEvent, request } from '../connector/fusionBridge';
import type { GlobalParam, PushResult } from '../types/types';

type ParamsListener = (params: GlobalParam[]) => void;
type BusyListener = (busy: boolean) => void;
type ReloadListener = () => void;

let params: GlobalParam[] = [];
let busy = false;
let watchStarted = false;
let initialLoad: Promise<GlobalParam[]> | null = null;
let loadErrorShown = false;

const paramsListeners = new Set<ParamsListener>();
const busyListeners = new Set<BusyListener>();
const projectReloadListeners = new Set<ReloadListener>();

function publishParams(next: GlobalParam[]) {
  params = next;
  paramsListeners.forEach((listener) => listener(params));
}

function publishBusy(next: boolean) {
  busy = next;
  busyListeners.forEach((listener) => listener(busy));
}

function subscribeGlobalParams(listener: ParamsListener): () => void {
  paramsListeners.add(listener);
  return () => {
    paramsListeners.delete(listener);
  };
}

function subscribeBusy(listener: BusyListener): () => void {
  busyListeners.add(listener);
  return () => {
    busyListeners.delete(listener);
  };
}

/** Project tab reloads after the global table is pushed into the design. */
export function subscribeProjectReload(listener: ReloadListener): () => void {
  projectReloadListeners.add(listener);
  return () => {
    projectReloadListeners.delete(listener);
  };
}

function requestProjectReload() {
  projectReloadListeners.forEach((listener) => listener());
}

function watchGlobalStore() {
  if (watchStarted) return;
  watchStarted = true;
  onEvent('loadGlobal', (raw) => {
    try {
      publishParams(JSON.parse(raw) as GlobalParam[]);
    } catch {
      /* ignore malformed push */
    }
  });
}

/** Load the global store into the shared list that feeds the global param table. */
export async function loadGlobalParams(): Promise<GlobalParam[]> {
  const data = await request<GlobalParam[]>('global:list');
  const next = data ?? [];
  publishParams(next);
  return next;
}

function ensureGlobalParamsLoaded(): Promise<GlobalParam[]> {
  watchGlobalStore();
  if (!initialLoad) {
    loadErrorShown = false;
    initialLoad = loadGlobalParams().catch((error) => {
      initialLoad = null;
      throw error;
    });
  }
  return initialLoad;
}

/**
 * Shared global-parameter state.
 * The header sync button and the global table refresh both call `pushToDesign`,
 * which reloads this list and then writes it into the active design.
 */
export function useGlobalParams() {
  const { showToast } = useToast();
  const [current, setCurrent] = useState<GlobalParam[]>(params);
  const [isBusy, setIsBusy] = useState(busy);

  useEffect(() => subscribeGlobalParams(setCurrent), []);
  useEffect(() => subscribeBusy(setIsBusy), []);

  useEffect(() => {
    void ensureGlobalParamsLoaded().catch((error) => {
      if (loadErrorShown) return;
      loadErrorShown = true;
      showToast(`Failed to load global parameters: ${String(error)}`, 'error');
    });
  }, [showToast]);

  const pushToDesign = useCallback(async () => {
    publishBusy(true);
    try {
      const data = await loadGlobalParams();
      if (data.length === 0) {
        showToast('No global parameters to push.', 'error');
        return;
      }
      const result = await request<PushResult>('global:pushToDesign', { params: data });
      requestProjectReload();
      const { created, updated, errors } = result;
      if (errors.length) {
        showToast(`Pushed with ${errors.length} error(s): ${errors[0]}`, 'error');
      } else {
        showToast(`Pushed to design (${created} created, ${updated} updated).`, 'success');
      }
    } catch (error) {
      showToast(`Push failed: ${String(error)}`, 'error');
    } finally {
      publishBusy(false);
    }
  }, [showToast]);

  return {
    params: current,
    setParams: publishParams,
    busy: isBusy,
    pushToDesign,
  };
}
