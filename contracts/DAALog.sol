// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title DAALog
/// @notice Minimal decentralized audit anchor for Zero Trust authorization decisions.
/// @dev Records are append-only. There are no admin edit or delete functions.
contract DAALog {
    struct AuditRecord {
        string agentId;
        bytes32 actionHash;
        uint256 timestamp;
        string metadata;
    }

    uint256 public recordCount;
    mapping(uint256 => AuditRecord) public records;

    event ActionLogged(
        uint256 indexed recordId,
        string indexed agentId,
        bytes32 indexed actionHash,
        uint256 timestamp,
        string metadata
    );

    function logAction(string calldata agentId, bytes32 actionHash, string calldata metadata) public returns (uint256) {
        require(bytes(agentId).length > 0, "agentId required");
        require(actionHash != bytes32(0), "actionHash required");

        uint256 recordId = recordCount;
        recordCount = recordId + 1;
        records[recordId] = AuditRecord({
            agentId: agentId,
            actionHash: actionHash,
            timestamp: block.timestamp,
            metadata: metadata
        });

        emit ActionLogged(recordId, agentId, actionHash, block.timestamp, metadata);
        return recordId;
    }

    function logBatch(string calldata agentId, bytes32 merkleRoot, string calldata metadata) external returns (uint256) {
        return logAction(agentId, merkleRoot, metadata);
    }
}
