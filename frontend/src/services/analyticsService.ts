/**
 * AGGRIX MTA Layer — Real Analytics API Service
 *
 * Connects frontend dashboard views to real FastAPI analytics endpoints:
 * - Merchant Single-Store Analytics: /api/v1/analytics/tenants/{tenant_id}/*
 * - Manager Multi-Store Analytics:   /api/v1/analytics/manager/*
 * - Platform Administration:         /api/v1/analytics/platform/*
 *
 * Implements token injection from localStorage, parameter serialization,
 * error mapping, and graceful handling of empty or loading states.
 */

import { apiClient } from './api'
import { getStoredToken } from './authService'
import type {
  ApiRequestOptions,
  TenantListResponse,
  TenantOverviewResponse,
  TenantSummaryResponse,
  TenantDailyMetricsResponse,
  TenantProductMetricsResponse,
  OrderStatusDistributionResponse,
  RecentOrdersResponse,
  ManagerSummaryResponse,
  ManagerStoresResponse,
  ManagerCompareResponse,
  PlatformSummaryResponse,
} from '../types/api'

export interface DateFilterParams {
  start_date?: string
  end_date?: string
  currency?: string
}

export interface PaginationParams {
  page?: number
  page_size?: number
}

function withAuthToken(options?: ApiRequestOptions): ApiRequestOptions {
  const token = options?.token ?? getStoredToken()
  return {
    ...options,
    token,
  }
}

// ---------------------------------------------------------------------------
// 1. Tenant Store Directory
// ---------------------------------------------------------------------------

/**
 * Retrieves the list of authorized stores accessible to the authenticated user.
 * GET /api/v1/analytics/tenants
 */
export async function fetchTenants(options?: ApiRequestOptions): Promise<TenantListResponse> {
  return apiClient.get<TenantListResponse>('/api/v1/analytics/tenants', withAuthToken(options))
}

// ---------------------------------------------------------------------------
// 2. Merchant Store Analytics Endpoints
// ---------------------------------------------------------------------------

/**
 * Retrieves the composite tenant dashboard overview.
 * GET /api/v1/analytics/tenants/{tenant_id}/overview
 */
export async function fetchTenantOverview(
  tenantId: string,
  params?: DateFilterParams,
  options?: ApiRequestOptions
): Promise<TenantOverviewResponse> {
  return apiClient.get<TenantOverviewResponse>(
    `/api/v1/analytics/tenants/${tenantId}/overview`,
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves tenant KPI summary rollups (orders, gross sales, net sales, AOV).
 * GET /api/v1/analytics/tenants/{tenant_id}/summary
 */
export async function fetchTenantSummary(
  tenantId: string,
  params?: DateFilterParams,
  options?: ApiRequestOptions
): Promise<TenantSummaryResponse> {
  return apiClient.get<TenantSummaryResponse>(
    `/api/v1/analytics/tenants/${tenantId}/summary`,
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves daily aggregated time-series metrics.
 * GET /api/v1/analytics/tenants/{tenant_id}/daily
 */
export async function fetchTenantDailyMetrics(
  tenantId: string,
  params?: DateFilterParams & PaginationParams,
  options?: ApiRequestOptions
): Promise<TenantDailyMetricsResponse> {
  return apiClient.get<TenantDailyMetricsResponse>(
    `/api/v1/analytics/tenants/${tenantId}/daily`,
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        page: params?.page,
        page_size: params?.page_size,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves product-level metrics ordered by gross sales descending.
 * GET /api/v1/analytics/tenants/{tenant_id}/products
 */
export async function fetchTenantProducts(
  tenantId: string,
  params?: DateFilterParams & PaginationParams,
  options?: ApiRequestOptions
): Promise<TenantProductMetricsResponse> {
  return apiClient.get<TenantProductMetricsResponse>(
    `/api/v1/analytics/tenants/${tenantId}/products`,
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        page: params?.page,
        page_size: params?.page_size,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves order status distribution breakdown.
 * GET /api/v1/analytics/tenants/{tenant_id}/status-distribution
 */
export async function fetchTenantStatusDistribution(
  tenantId: string,
  params?: DateFilterParams,
  options?: ApiRequestOptions
): Promise<OrderStatusDistributionResponse> {
  return apiClient.get<OrderStatusDistributionResponse>(
    `/api/v1/analytics/tenants/${tenantId}/status-distribution`,
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves chronological recent orders activity feed.
 * GET /api/v1/analytics/tenants/{tenant_id}/recent-orders
 */
export async function fetchTenantRecentOrders(
  tenantId: string,
  params?: PaginationParams,
  options?: ApiRequestOptions
): Promise<RecentOrdersResponse> {
  return apiClient.get<RecentOrdersResponse>(
    `/api/v1/analytics/tenants/${tenantId}/recent-orders`,
    withAuthToken({
      ...options,
      params: {
        page: params?.page,
        page_size: params?.page_size,
        ...options?.params,
      },
    })
  )
}

// ---------------------------------------------------------------------------
// 3. Manager Multi-Store Analytics Endpoints
// ---------------------------------------------------------------------------

export interface ManagerQueryParams extends DateFilterParams {
  tenant_ids?: string[]
}

/**
 * Retrieves aggregate performance metrics across all assigned stores for a manager.
 * GET /api/v1/analytics/manager/summary
 */
export async function fetchManagerSummary(
  params?: ManagerQueryParams,
  options?: ApiRequestOptions
): Promise<ManagerSummaryResponse> {
  return apiClient.get<ManagerSummaryResponse>(
    '/api/v1/analytics/manager/summary',
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        tenant_ids: params?.tenant_ids ? params.tenant_ids.join(',') : undefined,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves individual store performance rollups for all assigned stores.
 * GET /api/v1/analytics/manager/stores
 */
export async function fetchManagerStores(
  params?: DateFilterParams,
  options?: ApiRequestOptions
): Promise<ManagerStoresResponse> {
  return apiClient.get<ManagerStoresResponse>(
    '/api/v1/analytics/manager/stores',
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        ...options?.params,
      },
    })
  )
}

/**
 * Retrieves side-by-side store comparisons across assigned stores.
 * GET /api/v1/analytics/manager/compare
 */
export async function fetchManagerCompare(
  params?: ManagerQueryParams,
  options?: ApiRequestOptions
): Promise<ManagerCompareResponse> {
  return apiClient.get<ManagerCompareResponse>(
    '/api/v1/analytics/manager/compare',
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        tenant_ids: params?.tenant_ids,
        ...options?.params,
      },
    })
  )
}

// ---------------------------------------------------------------------------
// 4. Platform Administrator Analytics Endpoints
// ---------------------------------------------------------------------------

/**
 * Retrieves platform-wide analytics summary across all tenants in the system.
 * GET /api/v1/analytics/platform/summary
 */
export async function fetchPlatformSummary(
  params?: DateFilterParams,
  options?: ApiRequestOptions
): Promise<PlatformSummaryResponse> {
  return apiClient.get<PlatformSummaryResponse>(
    '/api/v1/analytics/platform/summary',
    withAuthToken({
      ...options,
      params: {
        start_date: params?.start_date,
        end_date: params?.end_date,
        currency: params?.currency,
        ...options?.params,
      },
    })
  )
}

export const analyticsService = {
  fetchTenants,
  fetchTenantOverview,
  fetchTenantSummary,
  fetchTenantDailyMetrics,
  fetchTenantProducts,
  fetchTenantStatusDistribution,
  fetchTenantRecentOrders,
  fetchManagerSummary,
  fetchManagerStores,
  fetchManagerCompare,
  fetchPlatformSummary,
}
