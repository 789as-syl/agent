"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.conversationsApi = void 0;
const client_1 = require("./client");
const module_factories_1 = require("@shared/api/module-factories");
exports.conversationsApi = (0, module_factories_1.createConversationsApi)(client_1.apiClient);
