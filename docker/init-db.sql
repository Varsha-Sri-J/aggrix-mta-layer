-- Create test database alongside primary application database
SELECT 'CREATE DATABASE aggrix_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'aggrix_test')\gexec

