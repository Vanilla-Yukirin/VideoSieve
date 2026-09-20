import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

const STORAGE_KEY = "videosieve_project_index";

export function useProjectIndex() {
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    const stored = localStorage.getItem(STORAGE_KEY);
    let cachedProjectIds: string[] = [];
    if (stored) {
      try {
        const parsed: unknown = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          cachedProjectIds = Array.from(
            new Set(parsed.filter((item): item is string => typeof item === "string")),
          );
        }
      } catch (e) {
        console.error("Failed to parse project index", e);
      }
    }

    void api.listProjects()
      .then((projects) => {
        if (cancelled) return;
        const persistedIds = projects.map((project) => project.project_id);
        setProjectIds(persistedIds);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(persistedIds));
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // The old browser index remains a migration/failure fallback only. A successful
        // API response always replaces it with SQLite's authoritative project list.
        setProjectIds(cachedProjectIds);
        setLoadError(error);
      })
      .finally(() => {
        if (!cancelled) setIsLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const addProject = useCallback((projectId: string) => {
    setProjectIds((prev) => {
      if (prev.includes(projectId)) return prev;
      const next = [projectId, ...prev];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const removeProject = useCallback((projectId: string) => {
    setProjectIds((prev) => {
      const next = prev.filter((id) => id !== projectId);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  return { projectIds, addProject, removeProject, isLoaded, loadError };
}
