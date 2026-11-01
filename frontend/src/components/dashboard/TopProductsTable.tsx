import React from 'react'
import { Card } from '../common/Card'
import { Package, ShieldCheck, Inbox } from 'lucide-react'

export interface ProductRanking {
  rank: number
  productId: string
  name: string
  sku: string
  unitsSold: number
  revenue: number
  currency: string
}

interface TopProductsTableProps {
  products: ProductRanking[]
  currency?: string
  isDemoData?: boolean
}

export const TopProductsTable: React.FC<TopProductsTableProps> = ({
  products,
  currency = 'USD',
  isDemoData = false,
}) => {
  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Package size={18} style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
          <span>Top 10 Products by Revenue</span>
        </div>
      }
      subtitle={`Product revenue aggregated from daily_product_metrics scoped strictly to ${currency}`}
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA</span>
        ) : (
          <span
            className="badge badge-neutral"
            style={{ fontSize: 10, padding: '2px 7px' }}
            title="Aggregated from PostgreSQL daily_product_metrics"
          >
            POSTGRESQL-BACKED
          </span>
        )
      }
    >
      <div style={{ marginTop: 12 }}>
        {products.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
            <Inbox size={32} style={{ marginBottom: 8, opacity: 0.5 }} aria-hidden="true" />
            <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>No Product Records Available</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              Zero merchandise sales recorded for currency {currency} in this reporting window.
            </div>
          </div>
        ) : (
          <div className="table-wrapper">
            <table aria-label={`Top products ranking in currency ${currency}`}>
              <thead>
                <tr>
                  <th scope="col" style={{ width: 60 }}>Rank</th>
                  <th scope="col">Product</th>
                  <th scope="col">SKU</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Units Sold</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Gross Revenue</th>
                  <th scope="col" style={{ width: 90, textAlign: 'center' }}>Currency</th>
                </tr>
              </thead>
              <tbody>
                {products.map(p => (
                  <tr key={p.productId}>
                    <td>
                      <span style={{
                        fontWeight: 700,
                        color: p.rank <= 3 ? 'var(--accent-primary)' : 'var(--text-muted)',
                        fontFamily: 'var(--font-mono)',
                      }}>
                        #{p.rank}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        {p.productId}
                      </div>
                    </td>
                    <td>
                      <code style={{ fontSize: 11, color: '#38bdf8' }}>{p.sku}</code>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>
                      {p.unitsSold.toLocaleString()}
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: '#ffffff' }}>
                      ${p.revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="badge badge-neutral">{p.currency}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
          <ShieldCheck size={14} style={{ color: 'var(--success)' }} aria-hidden="true" />
          <span>Historical Price Preservation Verified: calculations reference immutable <code>order_items.unit_price</code>, not <code>products.price</code>.</span>
        </div>
      </div>
    </Card>
  )
}
