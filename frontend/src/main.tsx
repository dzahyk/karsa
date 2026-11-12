import "@fontsource-variable/inter";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { ApiError } from "./api";
import { AppShell, homeFor, MorePage, RequireModule } from "./components/AppShell";
import { ToastProvider } from "./components/ui";
import { ActivityPage } from "./pages/ActivityPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AuditPage } from "./pages/AuditPage";
import { ManagePage } from "./pages/ManagePage";
import { CaseLayout } from "./pages/CaseLayout";
import { CasesPage } from "./pages/CasesPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FeasibilityPage } from "./pages/FeasibilityPage";
import { ImpactPage } from "./pages/ImpactPage";
import { NotFound } from "./pages/NotFound";
import { PackagePage } from "./pages/PackagePage";
import { RequirementsPage } from "./pages/RequirementsPage";
import { ReviewPage } from "./pages/ReviewPage";
import { RunPage } from "./pages/RunPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { SessionProvider, useSession } from "./session";

function Home() {
  const { user } = useSession();
  return <Navigate to={homeFor(user?.modules ?? [])} replace />;
}

const guard = (module: string, el: JSX.Element) => <RequireModule module={module}>{el}</RequireModule>;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2,
      refetchOnWindowFocus: false,
      staleTime: 5_000,
    },
  },
});

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: "cases", element: guard("cases", <CasesPage />) },
      {
        path: "cases/:code",
        element: guard("cases", <CaseLayout />),
        children: [
          { index: true, element: <Navigate to="requirements" replace /> },
          { path: "requirements", element: <RequirementsPage /> },
          { path: "feasibility", element: <FeasibilityPage /> },
          { path: "package", element: <PackagePage /> },
          { path: "activity", element: <ActivityPage /> },
        ],
      },
      { path: "approvals", element: guard("approvals", <ApprovalsPage />) },
      { path: "approvals/:packageId", element: guard("cases", <ReviewPage />) },
      { path: "workflows", element: guard("workflows", <WorkflowsPage />) },
      { path: "workflows/:runCode", element: guard("workflows", <RunPage />) },
      { path: "evaluation", element: guard("evaluation", <EvaluationPage />) },
      { path: "impact", element: guard("impact", <ImpactPage />) },
      { path: "audit", element: guard("audit", <AuditPage />) },
      { path: "manage", element: guard("manage", <ManagePage />) },
      { path: "more", element: <MorePage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </SessionProvider>
    </QueryClientProvider>
  </StrictMode>,
);
