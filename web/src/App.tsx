import { createBrowserRouter, RouterProvider } from "react-router";
import Shell from "@/components/Shell";
import AdminPage from "@/pages/AdminPage";
import IndexPage from "@/pages/IndexPage";
import InboxPage from "@/pages/InboxPage";

// §8.2: client-side routing with `createBrowserRouter`; nginx `try_files … /index.html`.
// The project/selector/question/claim/source routes land with R3/R4.
const router = createBrowserRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <IndexPage /> },
      { path: "inbox", element: <InboxPage /> },
      { path: "admin", element: <AdminPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
