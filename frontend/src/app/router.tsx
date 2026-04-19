import {
  Navigate,
  createBrowserRouter,
  createMemoryRouter,
  type RouteObject,
} from "react-router-dom";

import { AppLayout } from "./layout";
import { apiClient, type AppApi } from "../lib/api";
import { DashboardRoute } from "../routes/dashboard";
import { ActionNeededRoute } from "../routes/action-needed";
import { ApplicationRunLogRoute } from "../routes/application-run-log";
import { JobDetailRoute } from "../routes/job-detail";
import { JobsRoute } from "../routes/jobs";
import { LoginRoute } from "../routes/login";
import { QuestionsRoute } from "../routes/questions";
import { RoleProfileRoute } from "../routes/role-profile";
import { SourcesRoute } from "../routes/sources";
import { SystemLogRoute } from "../routes/system-log";

export function buildRoutes(api: AppApi = apiClient): RouteObject[] {
  return [
    {
      path: "/login",
      element: <LoginRoute api={api} />,
    },
    {
      path: "/",
      element: <AppLayout api={api} />,
      children: [
        {
          index: true,
          element: <DashboardRoute />,
        },
        {
          path: "jobs",
          element: <JobsRoute />,
        },
        {
          path: "jobs/:jobId",
          element: <JobDetailRoute />,
        },
        {
          path: "sources",
          element: <SourcesRoute />,
        },
        {
          path: "answers",
          element: <Navigate to="/role-profile?tab=answers" replace />,
        },
        {
          path: "questions",
          element: <QuestionsRoute />,
        },
        {
          path: "action-needed",
          element: <ActionNeededRoute />,
        },
        {
          path: "role-profile",
          element: <RoleProfileRoute />,
        },
        {
          path: "system-log",
          element: <SystemLogRoute />,
        },
        {
          path: "applications/runs/:runId/log",
          element: <ApplicationRunLogRoute />,
        },
      ],
    },
  ];
}

export function createBrowserAppRouter(api: AppApi = apiClient) {
  return createBrowserRouter(buildRoutes(api));
}

export function createMemoryAppRouter(
  api: AppApi = apiClient,
  initialEntries: string[] = ["/"],
) {
  return createMemoryRouter(buildRoutes(api), { initialEntries });
}
