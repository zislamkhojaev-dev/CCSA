import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "ccsa_playground_v1";

export type PlaygroundPersistedState = {
  jobId: number | null;
  scenarioId: number | "";
  selectedFileId: number | null;
  useScenarioPrompt: boolean;
  customPrompt: string;
};

const defaultState: PlaygroundPersistedState = {
  jobId: null,
  scenarioId: "",
  selectedFileId: null,
  useScenarioPrompt: true,
  customPrompt: "",
};

function loadState(): PlaygroundPersistedState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultState;
    const parsed = JSON.parse(raw) as Partial<PlaygroundPersistedState>;
    return {
      jobId: typeof parsed.jobId === "number" ? parsed.jobId : null,
      scenarioId:
        typeof parsed.scenarioId === "number"
          ? parsed.scenarioId
          : parsed.scenarioId === ""
            ? ""
            : defaultState.scenarioId,
      selectedFileId:
        typeof parsed.selectedFileId === "number" ? parsed.selectedFileId : null,
      useScenarioPrompt:
        typeof parsed.useScenarioPrompt === "boolean"
          ? parsed.useScenarioPrompt
          : defaultState.useScenarioPrompt,
      customPrompt:
        typeof parsed.customPrompt === "string" ? parsed.customPrompt : "",
    };
  } catch {
    return defaultState;
  }
}

type PlaygroundContextValue = PlaygroundPersistedState & {
  setJobId: (id: number | null) => void;
  setScenarioId: (id: number | "") => void;
  setSelectedFileId: (id: number | null) => void;
  setUseScenarioPrompt: (v: boolean) => void;
  setCustomPrompt: (v: string) => void;
  clearSession: () => void;
};

const PlaygroundContext = createContext<PlaygroundContextValue | null>(null);

export function PlaygroundProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PlaygroundPersistedState>(loadState);

  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const setJobId = useCallback((jobId: number | null) => {
    setState((s) => ({
      ...s,
      jobId,
      selectedFileId: jobId === s.jobId ? s.selectedFileId : null,
    }));
  }, []);

  const setScenarioId = useCallback((scenarioId: number | "") => {
    setState((s) => ({ ...s, scenarioId }));
  }, []);

  const setSelectedFileId = useCallback((selectedFileId: number | null) => {
    setState((s) => ({ ...s, selectedFileId }));
  }, []);

  const setUseScenarioPrompt = useCallback((useScenarioPrompt: boolean) => {
    setState((s) => ({ ...s, useScenarioPrompt }));
  }, []);

  const setCustomPrompt = useCallback((customPrompt: string) => {
    setState((s) => ({ ...s, customPrompt }));
  }, []);

  const clearSession = useCallback(() => {
    setState(defaultState);
    sessionStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo(
    () => ({
      ...state,
      setJobId,
      setScenarioId,
      setSelectedFileId,
      setUseScenarioPrompt,
      setCustomPrompt,
      clearSession,
    }),
    [
      state,
      setJobId,
      setScenarioId,
      setSelectedFileId,
      setUseScenarioPrompt,
      setCustomPrompt,
      clearSession,
    ]
  );

  return (
    <PlaygroundContext.Provider value={value}>{children}</PlaygroundContext.Provider>
  );
}

export function usePlayground() {
  const ctx = useContext(PlaygroundContext);
  if (!ctx) {
    throw new Error("usePlayground must be used within PlaygroundProvider");
  }
  return ctx;
}
