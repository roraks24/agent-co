import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { Landing } from "./pages/Landing";
import { Docs } from "./pages/Docs";
import { About } from "./pages/About";
import { LiveStudio } from "./pages/LiveStudio";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Landing },
      { path: "docs", Component: Docs },
      { path: "about", Component: About },
      { path: "studio", Component: LiveStudio },
    ],
  },
]);
