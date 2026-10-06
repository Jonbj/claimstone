import { createBrowserRouter, RouterProvider } from "react-router";
import Shell from "@/components/Shell";
import AdminPage from "@/pages/AdminPage";
import IndexPage from "@/pages/IndexPage";
import InboxPage from "@/pages/InboxPage";
import NotFoundPage from "@/pages/NotFoundPage";
import SelectorPlaceholderPage from "@/pages/SelectorPlaceholderPage";

// §8.2: client-side routing with `createBrowserRouter`; nginx `try_files … /index.html`.
// The selector overview page is R4's deliverable; its route resolves to a placeholder so
// the index's rows link somewhere named.
const router = createBrowserRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <IndexPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "p/:project/f/:sel", element: <SelectorPlaceholderPage /> },
      { path: "p/:project/u/:sel", element: <SelectorPlaceholderPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
