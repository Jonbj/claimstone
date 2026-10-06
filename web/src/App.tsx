import { createBrowserRouter, RouterProvider } from "react-router";
import IndexPage from "@/pages/IndexPage";

// §8.2: client-side routing with `createBrowserRouter`; nginx `try_files … /index.html`.
// The project/selector/question/claim/source routes land with R3/R4.
const router = createBrowserRouter([
  {
    path: "/",
    element: <IndexPage />,
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
