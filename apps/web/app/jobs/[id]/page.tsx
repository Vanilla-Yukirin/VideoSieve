"use client";

import React from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useJobRealtime } from "@/lib/hooks/useJobRealtime";
import { LogViewer } from "@/components/LogViewer";
import { ControlPanel } from "@/components/ControlPanel";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { ArrowLeft, Wifi, WifiOff, FileText, Download } from "lucide-react";
import { cn } from "@/lib/utils";

export default function JobDetail() {
  const params = useParams();
  const jobId = params.id as string;
  const state = useJobRealtime(jobId);

  // Calculate generic progress bar color
  const progressColor = 
     state.status === "failed" ? "bg-red-500" :
     state.status === "succeeded" ? "bg-green-500" :
     "bg-primary";

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-6 max-w-6xl">
       {/* Header */}
       <div className="flex items-center justify-between">
         <div className="flex items-center gap-4">
            <Link href={state.project_id ? `/projects/${state.project_id}` : "/"}>
                <Button variant="ghost" size="icon">
                    <ArrowLeft className="h-5 w-5" />
                </Button>
            </Link>
            <div>
                <h1 className="text-2xl font-bold tracking-tight font-mono">{jobId}</h1>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                    <span>Status:</span>
                    <Badge variant={
                        state.status === "succeeded" ? "success" :
                        state.status === "failed" ? "destructive" :
                        state.status === "running" ? "default" : "secondary"
                    }>{state.status}</Badge>
                    
                    {state.isConnected ? (
                         <span className="flex items-center text-green-600 ml-2" title="Realtime Connected">
                            <Wifi className="h-3 w-3 mr-1" /> Live
                         </span>
                    ) : (
                        <span className="flex items-center text-yellow-600 ml-2" title="Polling Fallback">
                            <WifiOff className="h-3 w-3 mr-1" /> Offline (Polling)
                        </span>
                    )}
                </div>
            </div>
         </div>
         <ControlPanel jobId={jobId} status={state.status} />
       </div>

       {/* Progress Section */}
       <Card>
           <CardContent className="p-6 space-y-4">
                <div className="flex justify-between text-sm font-medium">
                    <span>Stage: {state.current_stage || "Initializing..."}</span>
                    <span>{state.progress.toFixed(1)}%</span>
                </div>
                <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                    <div 
                        className={cn("h-full transition-all duration-500 ease-out", progressColor)}
                        style={{ width: `${state.progress}%` }}
                    />
                </div>
           </CardContent>
       </Card>

       <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
           {/* Logs - Takes up 2 cols */}
           <div className="lg:col-span-2 flex flex-col gap-4">
               <h3 className="text-lg font-semibold">Realtime Logs</h3>
               <LogViewer logs={state.latest_logs} className="h-[500px]" />
           </div>

           {/* Sidebar: Artifacts & Info */}
           <div className="space-y-6">
               <Card>
                   <CardHeader>
                       <CardTitle className="text-lg">Artifacts</CardTitle>
                   </CardHeader>
                   <CardContent>
                       {state.artifacts.length === 0 ? (
                           <p className="text-sm text-muted-foreground italic">No artifacts yet.</p>
                       ) : (
                           <ul className="space-y-2">
                               {state.artifacts.map((art) => (
                                   <li key={art.path} className="flex items-center justify-between text-sm p-2 rounded hover:bg-accent group">
                                       <div className="flex items-center truncate">
                                           <FileText className="h-4 w-4 mr-2 text-muted-foreground" />
                                           <span className="truncate max-w-[150px]" title={art.path}>{art.path.split('/').pop()}</span>
                                       </div>
                                       <a 
                                         href={`/api/workspace/${state.project_id}/${art.path}`} // Hypothetical download link if API supported it directly
                                         target="_blank" 
                                         rel="noopener noreferrer"
                                         className="opacity-0 group-hover:opacity-100 transition-opacity"
                                       >
                                           <Download className="h-4 w-4" />
                                       </a>
                                   </li>
                               ))}
                           </ul>
                       )}
                   </CardContent>
               </Card>
           </div>
       </div>
    </div>
  );
}
