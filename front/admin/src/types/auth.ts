export interface User {
  id: string
  phone: string
  role: 'user' | 'admin'
  created_at: string
  updated_at: string
}

export interface RegisterRequest {
  phone: string
  password: string
}

export interface LoginRequest {
  phone: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  access_expires_in: number
}

export interface RefreshTokenRequest {
  refresh_token?: string
}

export interface RefreshTokenResponse {
  access_token: string
  token_type: string
  access_expires_in: number
}
