import { createBrowserRouter, RouterProvider } from "react-router";
import Shell from "@/components/Shell";
import AdminPage from "@/pages/AdminPage";
import FlowOverviewPage from "@/pages/FlowOverviewPage";
import IndexPage from "@/pages/IndexPage";
import InboxPage from "@/pages/InboxPage";
import NotFoundPage from "@/pages/NotFoundPage";
import ProjectPage from "@/pages/ProjectPage";

// §8.2: client-side routing with `createBrowserRouter`; nginx `try_files … /index.html`.
// The selector overview is R4's deliverable; `f`/`u` are a prop so the page never
// guesses the kind. The question/claim/source routes land with their pages below.
const router = createBrowserRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <IndexPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "p/:project", element: <ProjectPage /> },
      { path: "p/:project/f/:sel", element: <FlowOverviewPage kind="f" /> },
      { path: "p/:project/u/:sel", element: <FlowOverviewPage kind="u" /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
