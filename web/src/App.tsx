import { createBrowserRouter, RouterProvider } from "react-router";
import Shell from "@/components/Shell";
import AdminPage from "@/pages/AdminPage";
import { SessionProvider } from "@/lib/session";
import ClaimPage from "@/pages/ClaimPage";
import FlowOverviewPage from "@/pages/FlowOverviewPage";
import IndexPage from "@/pages/IndexPage";
import InboxPage from "@/pages/InboxPage";
import LoginPage from "@/pages/LoginPage";
import NotFoundPage from "@/pages/NotFoundPage";
import ProjectPage from "@/pages/ProjectPage";
import QuestionPage from "@/pages/QuestionPage";
import SourcePage from "@/pages/SourcePage";

// §8.2: client-side routing with `createBrowserRouter`; nginx `try_files … /index.html`.
// `f`/`u` are a prop so no page ever guesses the selector kind; the question, claim and
// source routes repeat the pair so `api.selectorPath` is the only place that builds paths.
const router = createBrowserRouter([
  {
    path: "/",
    // The provider sits inside the router so the login page can navigate, and above the Shell
    // so the sidebar and every page read the same session.
    element: (
      <SessionProvider>
        <Shell />
      </SessionProvider>
    ),
    children: [
      // F1: `/` is still the projects index; Today replaces it in F2. `/projects` is the
      // sidebar's Projects link.
      { index: true, element: <IndexPage /> },
      { path: "projects", element: <IndexPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "p/:project", element: <ProjectPage /> },
      { path: "p/:project/f/:sel", element: <FlowOverviewPage kind="f" /> },
      { path: "p/:project/u/:sel", element: <FlowOverviewPage kind="u" /> },
      { path: "p/:project/f/:sel/q/:qid", element: <QuestionPage kind="f" /> },
      { path: "p/:project/u/:sel/q/:qid", element: <QuestionPage kind="u" /> },
      { path: "p/:project/f/:sel/claim/:cid", element: <ClaimPage kind="f" /> },
      { path: "p/:project/u/:sel/claim/:cid", element: <ClaimPage kind="u" /> },
      { path: "p/:project/f/:sel/source/:key", element: <SourcePage kind="f" /> },
      { path: "p/:project/u/:sel/source/:key", element: <SourcePage kind="u" /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
