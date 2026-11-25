type FooterBarProps = {
  designName: string;
  onClose: () => void;
};

export function FooterBar({ designName, onClose }: FooterBarProps) {
  return (
    <footer id="sbl-footer" className="sbl-footer">
      <span id="sbl-footer-design" className="sbl-footerDesign" title={designName}>
        {designName}
      </span>
      <button id="sbl-close-button" type="button" className="sbl-btn sbl-btnClose" onClick={onClose}>
        Close
      </button>
    </footer>
  );
}
