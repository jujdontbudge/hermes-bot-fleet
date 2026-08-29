targetScope = 'subscription'

@description('Azure region selected by issue 10 live policy, SKU, and quota checks.')
@allowed(['westus'])
param location string = 'westus'

param resourceGroupName string = 'rg-hermes-fleet-prod'
param deploymentName string = 'hermes-fleet-runtime'
param adminUsername string = 'fleetadmin'
@secure()
param adminSshPublicKey string

var tags = {
  application: 'hermes-bot-fleet'
  environment: 'production'
  managedBy: 'bicep'
  issue: '10'
  dataClassification: 'restricted'
  publicInbound: 'prohibited'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module runtime 'runtime.bicep' = {
  name: deploymentName
  scope: resourceGroup
  params: {
    location: location
    adminUsername: adminUsername
    adminSshPublicKey: adminSshPublicKey
    tags: tags
  }
}

output resourceGroupName string = resourceGroup.name
output virtualMachineName string = runtime.outputs.virtualMachineName
output networkInterfaceName string = runtime.outputs.networkInterfaceName
output networkSecurityGroupName string = runtime.outputs.networkSecurityGroupName
output virtualNetworkName string = runtime.outputs.virtualNetworkName
output subnetName string = runtime.outputs.subnetName
output privateIpAddress string = runtime.outputs.privateIpAddress
