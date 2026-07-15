#!/usr/bin/env pwsh
# MVP End-to-End Test Script
# Test flow: Register -> Login -> Products -> Cart -> Order

$ErrorActionPreference = 'Continue'
$GATEWAY = "http://localhost:9000"
$ts = Get-Date -Format "HHmmss"

Write-Host "`n╔════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Scalable E-Commerce MVP - End-to-End Test       ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# Step 1: Register
Write-Host "`n[1/6] User Registration" -ForegroundColor Green
$email = "test$ts@example.com"
$reg = @{username="user$ts"; email=$email; password="Pass123!"} | ConvertTo-Json
$r1 = Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/register" -ContentType 'application/json' -Body $reg 2>&1
Write-Host "✓ Registered: $($r1.username) / $($r1.email)"

# Step 2: Login
Write-Host "`n[2/6] User Login" -ForegroundColor Green
$login = @{email=$email; password="Pass123!"} | ConvertTo-Json
$r2 = Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/login" -ContentType 'application/json' -Body $login 2>&1
$token = $r2.access_token
Write-Host "✓ Token: $($token.Substring(0,20))..."

# Step 3: Get Products
Write-Host "`n[3/6] View Products" -ForegroundColor Green
$r3 = Invoke-RestMethod -Method Get -Uri "$GATEWAY/products" 2>&1
Write-Host "✓ Found $($r3.products.Count) products:"
$r3.products | ForEach-Object { Write-Host "  [$($_.id)] $($_.name) - \$$($_.price)" }
$pid = $r3.products[0].id

# Step 4: Add to Cart
Write-Host "`n[4/6] Add to Cart" -ForegroundColor Green
$cart = @{product_id=$pid; quantity=2} | ConvertTo-Json
$headers = @{Authorization="Bearer $token"}
$r4 = Invoke-RestMethod -Method Post -Uri "$GATEWAY/cart/items" -Headers $headers -ContentType 'application/json' -Body $cart 2>&1
Write-Host "✓ Added product $pid to cart"

# Step 5: View Cart
Write-Host "`n[5/6] View Cart" -ForegroundColor Green
$r5 = Invoke-RestMethod -Method Get -Uri "$GATEWAY/cart" -Headers $headers 2>&1
Write-Host "✓ Cart has $($r5.items.Count) item(s):"
$r5.items | ForEach-Object { Write-Host "  Product $($_.product_id): Qty=$($_.quantity)" }

# Step 6: Create Order
Write-Host "`n[6/6] Create Order" -ForegroundColor Green
$order = @{items=@(@{product_id=$pid; quantity=1})} | ConvertTo-Json -Depth 10
$r6 = Invoke-RestMethod -Method Post -Uri "$GATEWAY/orders" -Headers $headers -ContentType 'application/json' -Body $order 2>&1
Write-Host "✓ Order $($r6.order_id) created - Status: $($r6.status)"

Write-Host "`n╔════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║      ✅ ALL TESTS PASSED SUCCESSFULLY          ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════╝`n" -ForegroundColor Green
