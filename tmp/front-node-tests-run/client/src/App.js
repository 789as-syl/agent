"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const react_router_dom_1 = require("react-router-dom");
const sonner_1 = require("sonner");
const ProtectedRoute_1 = require("./components/ProtectedRoute");
const MainLayout = (0, react_1.lazy)(() => Promise.resolve().then(() => require('./components/MainLayout')));
const LoginPage = (0, react_1.lazy)(() => Promise.resolve().then(() => require('./pages/LoginPage')));
const RegisterPage = (0, react_1.lazy)(() => Promise.resolve().then(() => require('./pages/RegisterPage')));
const ChatPage = (0, react_1.lazy)(() => Promise.resolve().then(() => require('./pages/ChatPage')));
const RouteFallback = () => (0, jsx_runtime_1.jsx)("div", { className: "min-h-screen bg-slate-50" });
function App() {
    return ((0, jsx_runtime_1.jsxs)(jsx_runtime_1.Fragment, { children: [(0, jsx_runtime_1.jsx)(sonner_1.Toaster, { position: "top-right", toastOptions: {
                    duration: 3000,
                    style: {
                        background: '#363636',
                        color: '#fff',
                    },
                } }), (0, jsx_runtime_1.jsx)(react_router_dom_1.BrowserRouter, { children: (0, jsx_runtime_1.jsx)(react_1.Suspense, { fallback: (0, jsx_runtime_1.jsx)(RouteFallback, {}), children: (0, jsx_runtime_1.jsxs)(react_router_dom_1.Routes, { children: [(0, jsx_runtime_1.jsxs)(react_router_dom_1.Route, { element: (0, jsx_runtime_1.jsx)(ProtectedRoute_1.PublicRoute, {}), children: [(0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { path: "/login", element: (0, jsx_runtime_1.jsx)(LoginPage, {}) }), (0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { path: "/register", element: (0, jsx_runtime_1.jsx)(RegisterPage, {}) })] }), (0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { element: (0, jsx_runtime_1.jsx)(ProtectedRoute_1.ProtectedRoute, {}), children: (0, jsx_runtime_1.jsxs)(react_router_dom_1.Route, { element: (0, jsx_runtime_1.jsx)(MainLayout, {}), children: [(0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { path: "/", element: (0, jsx_runtime_1.jsx)(ChatPage, {}) }), (0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { path: "/:id", element: (0, jsx_runtime_1.jsx)(ChatPage, {}) })] }) }), (0, jsx_runtime_1.jsx)(react_router_dom_1.Route, { path: "*", element: (0, jsx_runtime_1.jsx)(react_router_dom_1.Navigate, { to: "/", replace: true }) })] }) }) })] }));
}
exports.default = App;
