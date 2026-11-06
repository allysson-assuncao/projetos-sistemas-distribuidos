// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title DocumentRegistry
 * @notice Registro descentralizado de hashes criptograficos de documentos com controle de revogacao.
 */
contract DocumentRegistry {
    struct DocumentRecord {
        bool exists;
        bool isValid;
        uint256 timestamp;
        address registrant;
    }

    address public immutable owner;
    uint256 public totalRegistered;
    mapping(bytes32 => DocumentRecord) private documents;

    event DocumentRegistered(
        bytes32 indexed docHash,
        address indexed registrant,
        uint256 timestamp
    );

    event DocumentRevoked(
        bytes32 indexed docHash,
        address indexed revokedBy,
        uint256 timestamp
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not the owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Registra um novo hash de documento no estado on-chain.
     * @param docHash Hash SHA-256 / Keccak-256 (32 bytes) do documento original off-chain.
     */
    function registerDocument(bytes32 docHash) external {
        require(docHash != bytes32(0), "Invalid empty document hash");
        require(!documents[docHash].exists, "Document already registered");

        documents[docHash] = DocumentRecord({
            exists: true,
            isValid: true,
            timestamp: block.timestamp,
            registrant: msg.sender
        });
        totalRegistered += 1;

        emit DocumentRegistered(docHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Revoga a validade de um documento previamente registrado (restrito ao owner).
     * @param docHash Hash de 32 bytes do documento a ser revogado.
     */
    function revokeDocument(bytes32 docHash) external onlyOwner {
        require(documents[docHash].exists, "Document does not exist");
        require(documents[docHash].isValid, "Document already revoked");

        documents[docHash].isValid = false;

        emit DocumentRevoked(docHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Consulta gratuita (view) do estado de um documento pelo seu hash.
     */
    function verifyDocument(bytes32 docHash)
        external
        view
        returns (
            bool exists,
            bool isValid,
            uint256 timestamp,
            address registrant
        )
    {
        DocumentRecord memory doc = documents[docHash];
        return (doc.exists, doc.isValid, doc.timestamp, doc.registrant);
    }
}
