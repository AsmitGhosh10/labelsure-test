import { createBrowserRouter } from "react-router-dom";

import MainLayout from "../layouts/MainLayout";
import HomePage from "../pages/HomePage";
import UploadPage from "../pages/UploadPage";
import SearchPage from "../pages/SearchPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <MainLayout />,
    children: [
      {
        index: true,
        element: <HomePage/>,
      },

      {
        path: "upload",
        element: <UploadPage/>,
      },

      {
            path: "search",
            element: <SearchPage/>
      }
    ],
  },
]);
