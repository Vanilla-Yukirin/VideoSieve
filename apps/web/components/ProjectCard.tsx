import React from "react";
import Link from "next/link";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/Card";
import { Trash } from "lucide-react";
import useSWR from "swr";
import { ApiClientError, api } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface ProjectCardProps {
  projectId: string;
  onRemove: (id: string) => void;
}

export function ProjectCard({ projectId, onRemove }: ProjectCardProps) {
  const { t } = useI18n();
  const [autoRemoved, setAutoRemoved] = React.useState(false);
  const { data: project, error, isLoading } = useSWR(
    projectId ? `/projects/${projectId}` : null,
    () => api.getProject(projectId)
  );
  const isNotFound = error instanceof ApiClientError && error.code === "not_found";

  React.useEffect(() => {
    if (isNotFound && !autoRemoved) {
      onRemove(projectId);
      setAutoRemoved(true);
    }
  }, [isNotFound, autoRemoved, onRemove, projectId]);

  if (isLoading) {
    return (
      <Card className="animate-pulse">
        <CardHeader>
          <div className="h-6 w-1/3 bg-muted rounded" />
        </CardHeader>
        <CardContent>
          <div className="h-4 w-full bg-muted rounded mb-2" />
          <div className="h-4 w-2/3 bg-muted rounded" />
        </CardContent>
      </Card>
    );
  }

  // Handle 404 or Removed Project
  if (isNotFound || !project) {
    return (
      <Card className="border-dashed border-muted-foreground/50 bg-muted/50">
        <CardHeader>
          <CardTitle className="text-muted-foreground text-lg">{t("projectCard.unknown")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground break-all">{projectId}</p>
        </CardContent>
        <CardFooter>
          <Button variant="ghost" size="sm" onClick={() => onRemove(projectId)}>
            <Trash className="mr-2 h-4 w-4" /> {t("projectCard.remove")}
          </Button>
        </CardFooter>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border-destructive/40 bg-destructive/5">
        <CardHeader>
          <CardTitle className="text-muted-foreground text-lg">{t("projectCard.loadFailed")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground break-all">{projectId}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="transition-colors hover:border-primary/35 hover:bg-card">
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start gap-2">
            <CardTitle className="text-lg line-clamp-2" title={project.title}>
              {project.title || t("projectCard.untitled")}
            </CardTitle>
            <Badge variant={project.status === "running" ? "default" : "secondary"}>
                {project.status}
            </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-xs text-muted-foreground mb-4 space-y-1">
            <p className="font-mono">{t("project.idLabel")}: {project.project_id}</p>
            <p>{t("projectCard.created")}: {new Date(project.created_at).toLocaleDateString()}</p>
        </div>
        <Link href={`/projects/${project.project_id}`} passHref>
          <Button variant="outline" className="w-full">
            {t("projectCard.view")}
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
