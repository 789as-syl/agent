"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.chatRunsApi = void 0;
const client_1 = require("./client");
const module_factories_1 = require("@shared/api/module-factories");
exports.chatRunsApi = (0, module_factories_1.createChatRunsApi)(client_1.apiClient);
