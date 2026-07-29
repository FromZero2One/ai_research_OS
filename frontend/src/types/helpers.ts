/**
 * API type helpers — ergonomic wrappers around the auto-generated openapi-typescript.
 *
 * Usage:
 *   import type { ApiResponse } from '@/types/helpers'
 *   import type { operations } from '@/types/api'
 *
 *   type CompanyList = ApiResponse<'list_companies_api_v1_companies_get'>
 */

import type { operations } from './api'

/** Extract the 200 response JSON body from an operation. */
export type ApiResponse<Op extends keyof operations> =
  operations[Op]['responses'] extends { 200: { content: { 'application/json': infer T } } }
    ? T
    : never
