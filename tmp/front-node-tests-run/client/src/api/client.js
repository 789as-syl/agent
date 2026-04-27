"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.extractApiErrorMessage = exports.apiClient = void 0;
const axios_1 = require("axios");
const client_core_1 = require("@shared/api/client-core");
const moduleExports = (0, client_core_1.createApiClientModule)(axios_1.default);
exports.apiClient = moduleExports.apiClient;
exports.extractApiErrorMessage = moduleExports.extractApiErrorMessage;
