import { useCallback, useEffect, useMemo, useState } from "react";
import {
  runStartupSync,
  type StartupSyncOptions,
  type StartupSyncResult,
} from "../services/startupSync";

export type StartupSyncState = StartupSyncResult & {
  loading: boolean;
  retry: () => void;
};

const emptyResult: StartupSyncResult = {
  snapshot: { prayedIds: [], publishedPrayers: [], outboxEvents: [] },
  identitySession: null,
  remoteRepository: null,
  remoteEnabled: false,
  remotePrayers: [],
};

/**
 * Runs startup synchronization from the app lifecycle and exposes a small
 * state object for providers/screens. Local state can render immediately;
 * `loading` only describes the online bootstrap attempt.
 */
export function useStartupSync(options: StartupSyncOptions = {}): StartupSyncState {
  // Keep caller-provided option identity stable while avoiding a network retry
  // on every render. The individual fields are the intended dependencies.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableOptions = useMemo(() => options, [
    options.localRepository,
    options.identityClient,
    options.remoteEnabled,
    options.apiBaseUrl,
    options.apiTimeoutMs,
    options.deviceInstallId,
    options.listParams,
    options.createRemoteRepository,
  ]);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<StartupSyncState>({
    ...emptyResult,
    loading: true,
    retry: () => undefined,
  });
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    void runStartupSync(stableOptions)
      .then((result) => {
        if (active) setState({ ...result, loading: false, retry });
      })
      .catch((error: unknown) => {
        // A local repository failure should not crash the navigation tree.
        if (active) setState({ ...emptyResult, loading: false, remoteError: error, retry });
      });
    return () => { active = false; };
  }, [attempt, retry, stableOptions]);

  return state;
}
