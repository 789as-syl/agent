import { apiClient } from './client'
import { createAuthApi } from './module-factories'
import type {
  User,
  RegisterRequest,
  LoginRequest,
  LoginResponse,
  RefreshTokenRequest,
  RefreshTokenResponse,
} from '../types'

export const authApi = createAuthApi<
  User,
  RegisterRequest,
  LoginRequest,
  LoginResponse,
  RefreshTokenRequest,
  RefreshTokenResponse
>(apiClient)
