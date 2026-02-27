import { createRouter, createRoute, createRootRoute } from "@tanstack/react-router";
import { BASE_PATH } from "@/util/const";

import RootLayout from "@/layouts/RootLayout";
import Home from "@/pages/Home";
import New from "@/pages/New";
import Wizard from "@/pages/Wizard";
import NotFound from "@/pages/error/404";

const rootRoute = createRootRoute({
    component: RootLayout,
    notFoundComponent: NotFound,
});

const homeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: Home,
});

const newRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/new",
    component: New,
});

const wizardRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/$id/wizard",
    component: Wizard,
});

const routeTree = rootRoute.addChildren([homeRoute, newRoute, wizardRoute]);

export const router = createRouter({
    routeTree,
    basepath: BASE_PATH,
});

declare module "@tanstack/react-router" {
    interface Register {
        router: typeof router;
    }
}
