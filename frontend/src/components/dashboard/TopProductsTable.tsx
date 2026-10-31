import React from 'react'
import { Card } from '../common/Card'
import { Package, ShieldCheck } from 'lucide-react'

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
  isDemoData = true,
}) => {
  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Package size={18} style={{ color: 'var(--accent-primary)' }} />
          <span>Top 10 Products by Revenue (Contract A Preview)</span>
        </div>
      }
      subtitle={`Revenue calculated as SUM(order_items.quantity * order_items.unit_price) scoped strictly to ${currency}`}
      action={
        isDemoData ? (
          <span className="badge-demo">DEMO DATA — NOT LIVE</span>
        ) : undefined
      }
    >
      <div style={{ marginTop: 12 }}>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th style={{ width: 60 }}>Rank</th>
                <th>Product</th>
                <th>SKU</th>
                <th style={{ textAlign: 'right' }}>Units Sold</th>
                <th style={{ textAlign: 'right' }}>Gross Revenue</th>
                <th style={{ width: 90, textAlign: 'center' }}>Currency</th>
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

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
          <ShieldCheck size={14} style={{ color: 'var(--success)' }} />
          <span>Historical Price Preservation Verified: calculations reference immutable <code>order_items.unit_price</code>, not <code>products.price</code>.</span>
        </div>
      </div>
    </Card>
  )
}
