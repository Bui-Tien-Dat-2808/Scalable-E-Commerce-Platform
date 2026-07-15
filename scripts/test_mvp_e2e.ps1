# MVP End-to-End Test Script
# This script tests the complete flow: Register → Login → Products → Cart → Order
# Prerequisites: docker compose up -d (all services running)

$ErrorActionPreference = 'Continue'
$GATEWAY_URL = "http://localhost:9000"
$timestamp = Get-Date -Format "HHmmss"

Write-Host "╔════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Scalable E-Commerce MVP - End-to-End Test       ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Test helper function
function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Uri,
        [object]$Body,
        [hashtable]$Headers
    )
    Write-Host "Testing: $Name" -ForegroundColor Yellow
    try {
        $params = @{ Method = $Method; Uri = $Uri }
        if ($Headers) { $params.Headers = $Headers }
        if ($Body) {
            $params.ContentType = 'application/json'
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
        }
        $response = Invoke-RestMethod @params
        Write-Host "  ✓ Success" -ForegroundColor Green
        return $response
    }
    catch {
        Write-Host "  ✗ Failed: $_" -ForegroundColor Red
        return $null
    }
}

# ==================== STEP 1: Register User ====================
Write-Host "`n[1/6] USER REGISTRATION" -ForegroundColor Magenta
$user_email = "testuser-$timestamp@example.com"
$reg_body = @{
    username = "testuser$timestamp"
    email = $user_email
    password = "SecurePass123!"
}
$user = Test-Endpoint "Register user" "Post" "$GATEWAY_URL/users/auth/register" $reg_body
if ($user) {
    Write-Host "  Username: $($user.username)"
    Write-Host "  Email: $($user.email)"
} else {
    Write-Host "Registration failed. Exiting." -ForegroundColor Red
    exit 1
}

# ==================== STEP 2: Login ====================
Write-Host "`n[2/6] USER LOGIN" -ForegroundColor Magenta
$login_body = @{
    email = $user_email
    password = "SecurePass123!"
}
$login = Test-Endpoint "Login user" "Post" "$GATEWAY_URL/users/auth/login" $login_body
if ($login) {
    $token = $login.access_token
    $auth_headers = @{ Authorization = "Bearer $token" }
    Write-Host "  Token: $($token.Substring(0, 20))..."
    Write-Host "  User: $($login.user.username)"
} else {
    Write-Host "Login failed. Exiting." -ForegroundColor Red
    exit 1
}

# ==================== STEP 3: Get Products ====================
Write-Host "`n[3/6] VIEW PRODUCTS" -ForegroundColor Magenta
$products = Test-Endpoint "Get products" "Get" "$GATEWAY_URL/products" $null
if ($products) {
    Write-Host "  Found $($products.products.Count) products:"
    $products.products | ForEach-Object {
        Write-Host "    - [$($_.id)] $($_.name) - \$$($_.price) (Stock: $($_.stock))"
    }
    $product_id = $products.products[0].id
} else {
    Write-Host "Failed to get products." -ForegroundColor Red
    exit 1
}

# ==================== STEP 4: Add to Cart ====================
Write-Host "`n[4/6] ADD TO CART" -ForegroundColor Magenta
$cart_body = @{
    product_id = $product_id
    quantity = 2
}
$cart_result = Test-Endpoint "Add to cart" "Post" "$GATEWAY_URL/cart/items" $cart_body $auth_headers
if ($cart_result) {
    Write-Host "  Product ID: $product_id"
    Write-Host "  Quantity: 2"
    Write-Host "  Items in cart: $($cart_result.items.Count)"
} else {
    Write-Host "Failed to add to cart." -ForegroundColor Red
    exit 1
}

# ==================== STEP 5: View Cart ====================
Write-Host "`n[5/6] VIEW CART" -ForegroundColor Magenta
$cart_view = Test-Endpoint "Get cart" "Get" "$GATEWAY_URL/cart" $null $auth_headers
if ($cart_view) {
    Write-Host "  Cart contains $($cart_view.items.Count) item(s):"
    $cart_view.items | ForEach-Object {
        Write-Host "    - Product $($_.product_id): Qty=$($_.quantity)"
    }
} else {
    Write-Host "Failed to view cart." -ForegroundColor Red
    exit 1
}

# ==================== STEP 6: Create Order ====================
Write-Host "`n[6/6] CREATE ORDER" -ForegroundColor Magenta
# user_id is derived from the JWT, not the request body
$order_body = @{
    items = @(
        @{ product_id = $product_id; quantity = 1 }
    )
}
$order = Test-Endpoint "Create order" "Post" "$GATEWAY_URL/orders" $order_body $auth_headers
if ($order) {
    Write-Host "  Order ID: $($order.order_id)"
    Write-Host "  User: $($order.user_id)"
    Write-Host "  Status: $($order.status)"
    Write-Host "  Items: $($order.items.Count)"
} else {
    Write-Host "Failed to create order." -ForegroundColor Red
    exit 1
}

# ==================== SUMMARY ====================
Write-Host "`n╔════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          ✅ ALL TESTS PASSED SUCCESSFULLY        ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`nFlow Summary:" -ForegroundColor Green
Write-Host "  1. ✓ User Registration"
Write-Host "  2. ✓ User Login"
Write-Host "  3. ✓ Product Catalog"
Write-Host "  4. ✓ Cart Management"
Write-Host "  5. ✓ Order Creation"
Write-Host ""
Write-Host "Gateway URL: $GATEWAY_URL" -ForegroundColor Cyan
Write-Host ""