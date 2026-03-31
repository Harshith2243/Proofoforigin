// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract ProofOfOrigin {
    
    // This is like one page in our magic notebook
    struct ContentRecord {
        string contentHash;      // magic fingerprint of file
        string creatorName; 
        string contentType;      // who made it
        uint256 timestamp;       // when they made it
              // "human" or "AI"
    }
    
    // The notebook itself — stores all records
    mapping(string => ContentRecord) public records;
    
    // Event — like ringing a bell when something is saved!
event ContentRegistered(string contentHash, string creator, uint256 time, string contentType);
    
    // Function to REGISTER content (save to notebook)
    function registerContent(
        string memory _hash,
        string memory _creator,
        string memory _type
    ) public {
        
        // Make sure this fingerprint isn't already saved
        require(bytes(records[_hash].contentHash).length == 0, "Already registered!");
        
        // Save it in the notebook forever!
        records[_hash] = ContentRecord({
            contentHash: _hash,
            creatorName: _creator,
            timestamp: block.timestamp,
            contentType: _type
        });
        
        emit ContentRegistered(_hash, _creator, block.timestamp, _type);
    }
    
    // Function to VERIFY content (check the notebook)
    function verifyContent(string memory _hash) public view returns (
        string memory creator,
        uint256 timestamp,
        string memory contentType,
        bool exists
    ) {
        ContentRecord memory record = records[_hash];
        
        if (bytes(record.contentHash).length == 0) {
            return ("", 0, "", false);   // Not found!
        }
        
        return (record.creatorName, record.timestamp, record.contentType, true);
    }
}