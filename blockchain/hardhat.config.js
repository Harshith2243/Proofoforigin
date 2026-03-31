require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();  // ← this reads your .env file

module.exports = {
  solidity: "0.8.19",
  networks: {
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL,       // ← pulls from .env
      accounts: [process.env.PRIVATE_KEY]     // ← pulls from .env
    }
  }
};