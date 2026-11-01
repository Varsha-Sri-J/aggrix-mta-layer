/**
 * AGGRIX MTA Layer — Order Ingestion Service Client
 * Enterprise-grade client functions for live merchant order ingestion.
 */

import { apiClient } from './api'
import { getStoredToken } from './authService'
import type {
  ApiRequestOptions,
  OrderBatchIngestPayload,
  OrderBatchIngestResponse,
  OrderIngestPayload,
  OrderIngestResponse,
} from '../types/api'

/**
 * Attaches the currently stored JWT bearer token to API request options.
 */
function withAuthToken(options?: ApiRequestOptions): ApiRequestOptions {
  const token = options?.token ?? getStoredToken()
  return {
    ...options,
    token,
  }
}

/**
 * Submits a single live merchant order to POST /api/v1/ingest/orders.
 * Enforces tenant isolation on the backend.
 */
export async function ingestOrder(
  payload: OrderIngestPayload,
  options?: ApiRequestOptions
): Promise<OrderIngestResponse> {
  return apiClient.post<OrderIngestResponse>(
    '/api/v1/ingest/orders',
    payload,
    withAuthToken(options)
  )
}

/**
 * Submits a batch of live merchant orders to POST /api/v1/ingest/orders/batch.
 */
export async function ingestOrderBatch(
  payload: OrderBatchIngestPayload,
  options?: ApiRequestOptions
): Promise<OrderBatchIngestResponse> {
  return apiClient.post<OrderBatchIngestResponse>(
    '/api/v1/ingest/orders/batch',
    payload,
    withAuthToken(options)
  )
}

export const ingestService = {
  ingestOrder,
  ingestOrderBatch,
}
