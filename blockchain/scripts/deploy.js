const hre = require("hardhat");

async function main() {
  const ProofOfOrigin = await hre.ethers.getContractFactory("ProofOfOrigin");
  const contract = await ProofOfOrigin.deploy();

  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("Contract deployed at:", address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});