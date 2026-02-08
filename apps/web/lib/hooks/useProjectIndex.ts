import { useState, useEffect } from "react";

const STORAGE_KEY = "videosieve_project_index";

export function useProjectIndex() {
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        setProjectIds(JSON.parse(stored));
      } catch (e) {
        console.error("Failed to parse project index", e);
      }
    }
    setIsLoaded(true);
  }, []);

  const addProject = (projectId: string) => {
    setProjectIds((prev) => {
      if (prev.includes(projectId)) return prev;
      const next = [projectId, ...prev];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  const removeProject = (projectId: string) => {
    setProjectIds((prev) => {
      const next = prev.filter((id) => id !== projectId);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  };

  return { projectIds, addProject, removeProject, isLoaded };
}
