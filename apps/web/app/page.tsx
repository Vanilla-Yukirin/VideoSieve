"use client";

import React, { useState } from "react";
import { api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { Button } from "@/components/Button";
import { ProjectCard } from "@/components/ProjectCard";
import { PlusCircle } from "lucide-react";

export default function Home() {
  const { projectIds, addProject, removeProject, isLoaded } = useProjectIndex();
  const [isCreating, setIsCreating] = useState(false);
  const runtimeMode = api.getRuntimeMode();

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const { project_id } = await api.createProject({ title: "New Project " + new Date().toISOString() });
      addProject(project_id);
    } catch (e) {
      alert("Failed to create project");
      console.error(e);
    } finally {
      setIsCreating(false);
    }
  };

  if (!isLoaded) return null;

  return (
    <main className="container mx-auto p-4 md:p-8 space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground mt-1">Local index of your VideoSieve projects.</p>
        </div>
        <Button onClick={handleCreate} isLoading={isCreating}>
          <PlusCircle className="mr-2 h-4 w-4" /> New Project
        </Button>
      </div>

      {runtimeMode === "mock" ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Running in local mock mode. Start backend and set `NEXT_PUBLIC_API_MODE=remote` to use live API.
        </div>
      ) : null}

      {projectIds.length === 0 ? (
        <div className="text-center py-20 border-2 border-dashed rounded-lg">
          <p className="text-muted-foreground mb-4">No projects found in local index.</p>
          <Button onClick={handleCreate} isLoading={isCreating}>Create your first project</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {projectIds.map(id => (
                <ProjectCard key={id} projectId={id} onRemove={removeProject} />
            ))}
        </div>
      )}
    </main>
  );
}
