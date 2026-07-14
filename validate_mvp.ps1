#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Scalable E-Commerce MVP - Comprehensive End-to-End Validation Test
.DESCRIPTION
    Tests complete workflow: Registration -> Login -> Products -> Cart -> Order
    Validates all services through the API Gateway (port 9000)
#>

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Scalable E-Commerce MVP - End-to-End Validation Test   ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

$GATEWAY = "http://localhost:9000"
$timestamp = Get-Date -Format "HHmmss"
$testEmail = "mvptest$timestamp@example.com"
$testUser = "mvptest$timestamp"
$testPass = "TestPass123!"

Write-Host "`nGateway URL: $GATEWAY" -ForegroundColor Yellow
Write-Host "Test User: $testUser / $testEmail`n" -ForegroundColor Yellow

function Test-Step {
    param([string]$Step, [string]$Description)
    Write-Host "[$Step] $Description" -ForegroundColor Green
}

function Test-Success {
    param([string]$Message)
    Write-Host "  ✓ $Message" -ForegroundColor Green
}

function Test-Error {
    param([string]$Message)
    Write-Host "  ✗ $Message" -ForegroundColor Red
    exit 1
}

# ==================== STEP 1: USER REGISTRATION ====================
Test-Step "1/5" "USER REGISTRATION"

try {
    $regBody = @{
        username = $testUser
        email = $testEmail
        password = $testPass
    } | ConvertTo-Json
    
    $regResponse = Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/register" `
        -ContentType 'application/json' -Body $regBody -ErrorAction Stop
    
    Test-Success "User registered successfully"
    Write-Host "  User: $($regResponse.username)"
    Write-Host "  Email: $($regResponse.email)"
} catch {
    Test-Error "Registration failed: $_"
}

# ==================== STEP 2: USER LOGIN ====================
Test-Step "2/5" "USER LOGIN"

try {
    $loginBody = @{
        email = $testEmail
        password = $testPass
    } | ConvertTo-Json
    
    $loginResponse = Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/login" `
        -ContentType 'application/json' -Body $loginBody -ErrorAction Stop
    
    $token = $loginResponse.access_token
    $headers = @{ Authorization = "Bearer $token" }
    Test-Success "Login successful"
    Write-Host "  Token: $($token.Substring(0, 20))..."
    Write-Host "  User: $($loginResponse.user.username)"
} catch {
    Test-Error "Login failed: $_"
}

# ==================== STEP 3: GET PRODUCTS ====================
Test-Step "3/5" "PRODUCT CATALOG"

try {
    $productsResponse = Invoke-RestMethod -Method Get -Uri "$GATEWAY/products" -ErrorAction Stop
    
    $productCount = $productsResponse.products.Count
    Test-Success "Retrieved product catalog"
    Write-Host "  Total products: $productCount"
    
    if ($productCount -gt 0) {
        $productsResponse.products | ForEach-Object {
            Write-Host "    [$($_.id)] $($_.name) - `$$($_.price) (Stock: $($_.stock))"
        }
        $testProductId = $productsResponse.products[0].id
    } else {
        Test-Error "No products found in catalog"
    }
} catch {
    Test-Error "Product listing failed: $_"
}

# ==================== STEP 4: CART MANAGEMENT ====================
Test-Step "4/5" "SHOPPING CART"

try {
    $cartBody = @{
        product_id = $testProductId
        quantity = 2
    } | ConvertTo-Json
    
    $cartResponse = Invoke-RestMethod -Method Post -Uri "$GATEWAY/cart/items" `
        -Headers $headers -ContentType 'application/json' -Body $cartBody -ErrorAction Stop
    
    Test-Success "Item added to cart"
    Write-Host "  Product ID: $testProductId"
    Write-Host "  Quantity: 2"
    Write-Host "  Items in cart: $($cartResponse.items.Count)"
    
    # Verify cart contents
    $cartView = Invoke-RestMethod -Method Get -Uri "$GATEWAY/cart" -Headers $headers -ErrorAction Stop
    Test-Success "Cart retrieved successfully"
    Write-Host "  Cart items:"
    $cartView.items | ForEach-Object {
        Write-Host "    - Product $($_.product_id): Qty=$($_.quantity)"
    }
} catch {
    Test-Error "Cart operation failed: $_"
}

# ==================== STEP 5: ORDER CREATION ====================
Test-Step "5/5" "ORDER CREATION"

try {
    $orderBody = @{
        items = @(
            @{
                product_id = $testProductId
                quantity = 1
            }
        )
    } | ConvertTo-Json -Depth 10
    
    # user_id is derived from the JWT, not the request body
    $orderResponse = Invoke-RestMethod -Method Post -Uri "$GATEWAY/orders" `
        -Headers $headers -ContentType 'application/json' -Body $orderBody -ErrorAction Stop
    
    Test-Success "Order created successfully"
    Write-Host "  Order ID: $($orderResponse.order_id)"
    Write-Host "  User: $($orderResponse.user_id)"
    Write-Host "  Status: $($orderResponse.status)"
    Write-Host "  Items: $($orderResponse.items.Count)"
} catch {
    Test-Error "Order creation failed: $_"
}

# ==================== SUMMARY ====================
Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          ✅ ALL TESTS PASSED SUCCESSFULLY              ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`nValidation Summary:" -ForegroundColor Cyan
Write-Host "  ✓ User Service: Registration & Login working" -ForegroundColor Green
Write-Host "  ✓ Product Service: Catalog retrieval working" -ForegroundColor Green
Write-Host "  ✓ Cart Service: Shopping cart operations working" -ForegroundColor Green
Write-Host "  ✓ Order Service: Order creation working" -ForegroundColor Green
Write-Host "  ✓ API Gateway: Request routing working" -ForegroundColor Green
Write-Host "`n✅ MVP is production-ready for testing!" -ForegroundColor Green
Write-Host ""