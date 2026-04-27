"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.authApi = void 0;
const client_1 = require("./client");
const module_factories_1 = require("@shared/api/module-factories");
exports.authApi = (0, module_factories_1.createAuthApi)(client_1.apiClient);
