"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.retryIngestionJob = exports.getIngestionJob = exports.reindexKnowledgePoint = exports.updateKnowledgePoint = exports.getKnowledgePointDocumentUrl = exports.getKnowledgePoint = exports.createKnowledgePoint = exports.getKnowledgePoints = exports.uploadCallback = exports.presignUpload = exports.adminIngestionApi = void 0;
const client_1 = require("./client");
const module_factories_1 = require("@shared/api/module-factories");
const adminIngestionApi = (0, module_factories_1.createAdminIngestionApi)(client_1.apiClient);
exports.adminIngestionApi = adminIngestionApi;
exports.presignUpload = adminIngestionApi.presignUpload, exports.uploadCallback = adminIngestionApi.uploadCallback, exports.getKnowledgePoints = adminIngestionApi.getKnowledgePoints, exports.createKnowledgePoint = adminIngestionApi.createKnowledgePoint, exports.getKnowledgePoint = adminIngestionApi.getKnowledgePoint, exports.getKnowledgePointDocumentUrl = adminIngestionApi.getKnowledgePointDocumentUrl, exports.updateKnowledgePoint = adminIngestionApi.updateKnowledgePoint, exports.reindexKnowledgePoint = adminIngestionApi.reindexKnowledgePoint, exports.getIngestionJob = adminIngestionApi.getIngestionJob, exports.retryIngestionJob = adminIngestionApi.retryIngestionJob;
