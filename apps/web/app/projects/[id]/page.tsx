"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { ArrowLeft, PlayCircle, Clock } from "lucide-react";
import Link from "next/link";
import { IngestProbe } from "@/components/IngestProbe";
import { IngestParams } from "@/lib/api/types";

export default function ProjectDetail() {
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();
  const { addProject } = useProjectIndex();
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [ingestParams, setIngestParams] = useState<IngestParams | undefined>(undefined);

  const { data: project, error: projectError } = useSWR(
    projectId ? `/projects/${projectId}` : null,
    () => api.getProject(projectId)
  );

  const { data: jobs, mutate: refreshJobs } = useSWR(
    projectId ? `/projects/${projectId}/jobs` : null,
    () => api.getProjectJobs(projectId)
  );

  // Auto-add to index on visit if valid
  useEffect(() => {
    if (project) addProject(project.project_id);
  }, [project, addProject]);

  const handleCreateJob = async () => {
    setIsCreatingJob(true);
    try {
      const { job_id } = await api.createJob({ 
        project_id: projectId,
        ingest: ingestParams
      });
      await refreshJobs();
      router.push(`/jobs/${job_id}`);
    } catch (e) {
      console.error(e);
      alert("Failed to create job");
    } finally {
      setIsCreatingJob(false);
    }
  };

  if (projectError) {
    return (
      <div className="container mx-auto p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Project Not Found</h1>
        <Link href="/">
            <Button variant="outline">Go Back</Button>
        </Link>
      </div>
    );
  }

  if (!project) {
    return <div className="p-8">Loading project...</div>;
  }

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
           <h1 className="text-2xl font-bold tracking-tight">{project.title}</h1>
           <p className="text-muted-foreground text-sm">{project.project_id}</p>
        </div>
        <div className="ml-auto">
             <Badge variant={project.status === "running" ? "default" : "secondary"}>
                {project.status}
            </Badge>
        </div>
      </div>

      <div className="grid gap-6">
        <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <PlayCircle className="h-5 w-5 text-primary" />
                    New Job
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <IngestProbe onParamsReady={setIngestParams} disabled={isCreatingJob} />
                
                <div className="flex justify-end">
                    <Button 
                        onClick={handleCreateJob} 
                        isLoading={isCreatingJob}
                        disabled={!ingestParams?.source_url} // Require URL at minimum if user interacted
                    >
                        Start Download & Process
                    </Button>
                </div>
            </CardContent>
        </Card>

        <div>
            <h2 className="text-xl font-semibold mb-4">Job History</h2>
            <div className="space-y-4">
                {!jobs || jobs.length === 0 ? (
                    <div className="text-center py-10 text-muted-foreground border rounded-lg bg-muted/20">
                        No jobs run yet. Start one above!
                    </div>
                ) : (
                    jobs.slice().reverse().map(job => (
                        <Link href={`/jobs/${job.job_id}`} key={job.job_id} className="block group">
                            <Card className="group-hover:border-primary/50 transition-colors">
                                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                            <span className="font-mono font-medium">{job.job_id}</span>
                                            <Badge variant={
                                                job.status === "succeeded" ? "success" :
                                                job.status === "failed" ? "destructive" :
                                                job.status === "running" ? "default" : "secondary"
                                            }>{job.status}</Badge>
                                        </div>
                                        <div className="flex items-center text-xs text-muted-foreground gap-4">
                                            <span className="flex items-center"><Clock className="mr-1 h-3 w-3"/> {new Date(job.created_at).toLocaleString()}</span>
                                            {job.stage && <span>Stage: {job.stage}</span>}
                                        </div>
                                    </div>
                                    {job.error_message && (
                                        <div className="text-destructive text-sm max-w-md truncate">
                                            Error: {job.error_message}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </Link>
                    ))
                )}
            </div>
        </div>
      </div>
    </div>
  );
}
