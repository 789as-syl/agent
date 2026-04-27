"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ProtectedRoute = ProtectedRoute;
exports.PublicRoute = PublicRoute;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const store_1 = require("../store");
function ProtectedRoute() {
    const isAuthenticated = (0, store_1.useAuthStore)((state) => state.isAuthenticated);
    const accessToken = (0, store_1.useAuthStore)((state) => state.accessToken);
    const fetchMe = (0, store_1.useAuthStore)((state) => state.fetchMe);
    const [checking, setChecking] = (0, react_1.useState)(true);
    (0, react_1.useEffect)(() => {
        let active = true;
        const run = async () => {
            if (!isAuthenticated || !accessToken) {
                if (active)
                    setChecking(false);
                return;
            }
            try {
                await fetchMe();
            }
            catch {
                // handled in store
            }
            if (active)
                setChecking(false);
        };
        void run();
        return () => {
            active = false;
        };
    }, [isAuthenticated, accessToken, fetchMe]);
    if (checking) {
        return (0, jsx_runtime_1.jsx)("div", { className: "flex min-h-screen items-center justify-center text-sm text-slate-500", children: "\u4F1A\u8BDD\u6821\u9A8C\u4E2D..." });
    }
    if (!isAuthenticated || !accessToken) {
        return (0, jsx_runtime_1.jsx)(react_router_dom_1.Navigate, { to: "/login", replace: true });
    }
    return (0, jsx_runtime_1.jsx)(react_router_dom_1.Outlet, {});
}
function PublicRoute() {
    const isAuthenticated = (0, store_1.useAuthStore)((state) => state.isAuthenticated);
    const accessToken = (0, store_1.useAuthStore)((state) => state.accessToken);
    const user = (0, store_1.useAuthStore)((state) => state.user);
    if (isAuthenticated && accessToken && user) {
        return (0, jsx_runtime_1.jsx)(react_router_dom_1.Navigate, { to: "/", replace: true });
    }
    return (0, jsx_runtime_1.jsx)(react_router_dom_1.Outlet, {});
}
