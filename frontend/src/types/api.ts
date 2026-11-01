/**
 * AGGRIX MTA Layer — Type Definitions for Backend API & Engine
 */

export interface HealthResponse {
  status: 'healthy' | 'unhealthy'
  database: 'connected' | 'disconnected'
  environment: string
  error?: string | null
}

export interface RootMetaResponse {
  name: string
  version: string
  description: string
  environment: string
  status: string
  docs_url: string
}

export type EndpointStatus = 'available' | 'planned' | 'offline'

export interface EndpointSpec {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  path: string
  category: 'System & Health' | 'Authentication & RBAC' | 'Merchant Analytics' | 'Manager Analytics' | 'Platform Analytics'
  status: EndpointStatus
  description: string
  requestSchema?: string
  responseSchema?: string
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  baseUrl?: string
  params?: Record<string, string | number | boolean | undefined | null | Array<string | number | boolean>>
  body?: unknown
  token?: string | null
  signal?: AbortSignal
}

export interface ApiErrorDetail {
  message: string
  status: number
  statusText: string
  endpoint: string
  data?: unknown
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  role?: string
  tenant_ids?: string[]
}

export type FrontendRole = 'merchant' | 'manager' | 'admin'
export type BackendRole = 'tenant_user' | 'store_manager' | 'platform_admin'
export type UserRole = FrontendRole | BackendRole | string

export interface UserProfile {
  id: string
  email: string
  full_name?: string
  role: FrontendRole | string
  raw_role?: BackendRole | string
  active_tenant_id?: string | null
  assigned_tenants?: string[]
}

export interface AuthState {
  isAuthenticated: boolean
  user: UserProfile | null
  token: string | null
  backendSupported: boolean
  statusMessage: string
}

// ---------------------------------------------------------------------------
// Analytics & Financial Models (Matching FastAPI Backend Schemas)
// ---------------------------------------------------------------------------

export interface DateRangeFilter {
  start_date?: string | null
  end_date?: string | null
}

export interface CurrencySummary {
  currency: string
  total_orders: number
  gross_sales: number
  net_sales: number
  pending_orders_count: number
  pending_sales: number
  cancelled_orders_count: number
  cancelled_sales: number
  average_order_value?: number | null
}

export interface TenantSummaryResponse {
  tenant_id: string
  date_range: DateRangeFilter
  currency?: string | null
  total_orders: number
  gross_sales?: number | null
  net_sales?: number | null
  pending_orders_count?: number | null
  pending_sales?: number | null
  cancelled_orders_count?: number | null
  cancelled_sales?: number | null
  average_order_value?: number | null
  active_customers_count?: number | null
  currencies: CurrencySummary[]
}

export interface PaginationMeta {
  total_records: number
  page: number
  page_size: number
  total_pages: number
}

export interface DailyMetricRecord {
  metric_date: string
  currency: string
  orders_count: number
  gross_sales: number
  net_sales: number
  pending_orders_count: number
  pending_sales: number
  cancelled_orders_count: number
  cancelled_sales: number
}

export interface TenantDailyMetricsResponse {
  tenant_id: string
  date_range: DateRangeFilter
  currency?: string | null
  pagination: PaginationMeta
  data: DailyMetricRecord[]
}

export interface ProductMetricRecord {
  product_id: string
  product_name?: string | null
  product_sku?: string | null
  currency: string
  units_sold_gross: number
  units_sold_net: number
  pending_units: number
  cancelled_units: number
  gross_sales: number
  net_sales: number
  pending_sales: number
  cancelled_sales: number
  orders_count: number
}

export interface TenantProductMetricsResponse {
  tenant_id: string
  date_range: DateRangeFilter
  currency?: string | null
  pagination: PaginationMeta
  data: ProductMetricRecord[]
}

export interface OrderStatusMetric {
  status: string
  orders_count: number
  gross_sales: number
  percentage: number
}

export interface OrderStatusDistributionResponse {
  tenant_id: string
  date_range: DateRangeFilter
  currency?: string | null
  total_orders: number
  statuses: OrderStatusMetric[]
}

export interface RecentOrderRecord {
  id: string
  external_order_id: string
  customer_id: string
  customer_name?: string | null
  customer_email?: string | null
  status: string
  currency: string
  total_amount: number
  items_count: number
  created_at: string
}

export interface RecentOrdersResponse {
  tenant_id: string
  pagination: PaginationMeta
  data: RecentOrderRecord[]
}

export interface TenantListItem {
  id: string
  name: string
  domain: string
  timezone: string
  created_at: string
}

export interface TenantListResponse {
  total: number
  tenants: TenantListItem[]
}

export interface TenantOverviewResponse {
  tenant_id: string
  tenant_name: string
  tenant_domain: string
  summary: TenantSummaryResponse
  status_distribution: OrderStatusMetric[]
  recent_orders: RecentOrderRecord[]
  top_products: ProductMetricRecord[]
}

export interface ManagerSummaryResponse {
  manager_user_id: string
  assigned_tenants_count: number
  assigned_tenant_ids: string[]
  date_range: DateRangeFilter
  currency?: string | null
  total_orders: number
  gross_sales?: number | null
  net_sales?: number | null
  pending_orders_count?: number | null
  pending_sales?: number | null
  cancelled_orders_count?: number | null
  cancelled_sales?: number | null
  currencies: CurrencySummary[]
}

export interface StorePerformanceRecord {
  tenant_id: string
  tenant_name: string
  domain: string
  timezone: string
  total_orders: number
  gross_sales?: number | null
  net_sales?: number | null
  pending_orders_count?: number | null
  pending_sales?: number | null
  cancelled_orders_count?: number | null
  cancelled_sales?: number | null
  currency?: string | null
  currencies: CurrencySummary[]
}

export interface ManagerStoresResponse {
  manager_user_id: string
  total_stores: number
  date_range: DateRangeFilter
  currency?: string | null
  stores: StorePerformanceRecord[]
}

export interface ManagerCompareResponse {
  manager_user_id: string
  date_range: DateRangeFilter
  currency?: string | null
  compared_stores_count: number
  stores: StorePerformanceRecord[]
}

export interface PlatformSummaryResponse {
  total_tenants: number
  date_range: DateRangeFilter
  currency?: string | null
  total_orders: number
  gross_sales?: number | null
  net_sales?: number | null
  pending_orders_count?: number | null
  pending_sales?: number | null
  cancelled_orders_count?: number | null
  cancelled_sales?: number | null
  currencies: CurrencySummary[]
}

// ---------------------------------------------------------------------------
// Server-Sent Events (SSE) Models
// ---------------------------------------------------------------------------

export interface BroadcastEvent {
  id: string
  event_type: string
  tenant_id: string
  order_id: string
  external_order_id?: string | null
  status: string
  total_amount: number
  currency: string
  created_at: string
  timestamp: string
}

// ---------------------------------------------------------------------------
// Live Ingestion Models
// ---------------------------------------------------------------------------

export interface OrderItemIngestPayload {
  sku: string
  name?: string
  quantity: number
  unit_price: number
}

export interface CustomerIngestPayload {
  email: string
  name?: string
}

export interface OrderIngestPayload {
  tenant_id?: string
  external_order_id: string
  customer: CustomerIngestPayload
  currency?: string
  status?: 'pending' | 'paid' | 'fulfilled' | 'cancelled'
  created_at?: string
  items: OrderItemIngestPayload[]
  total_amount?: number
}

export interface OrderIngestResponse {
  order_id: string
  tenant_id: string
  external_order_id: string
  status: string
  currency: string
  total_amount: number
  items_count: number
  outbox_event_id: string
  event_type: string
  is_duplicate: boolean
  message: string
}

export interface OrderBatchIngestPayload {
  tenant_id?: string
  orders: OrderIngestPayload[]
}

export interface OrderBatchIngestResponse {
  tenant_id: string
  total_submitted: number
  ingested_count: number
  duplicate_count: number
  orders: OrderIngestResponse[]
}


