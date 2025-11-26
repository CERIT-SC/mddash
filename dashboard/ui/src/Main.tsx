import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Routes, Route, BrowserRouter } from "react-router-dom";

import "./Main.css";

import Layout from "./Layout";
import Home from "./pages/Home";
import New from "./pages/New";
import Wizard from "./pages/Wizard";
import NotFound from "./pages/error/404";
import { BASE_PATH } from "./util/const";

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <BrowserRouter basename={BASE_PATH}>
            <Routes>
                <Route path="/" element={<Layout />}>
                    <Route index element={<Home />} />
                    <Route path="/new" element={<New />} />
                    <Route path="/:id/wizard" element={<Wizard />} />
                    <Route path="*" element={<NotFound />} />
                </Route>
            </Routes>
        </BrowserRouter>
    </StrictMode>
);
