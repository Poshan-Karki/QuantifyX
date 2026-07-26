function Drop({ options = [], value, onChange, placeholder = "Select an option" }) {
  return (
    <select value={value} onChange={onChange}>
      <option value="">{placeholder}</option>
      {options.map((option) => {
        const optionValue = typeof option === "object" ? option.value : option;
        const optionLabel = typeof option === "object" ? option.label : option;
        return (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        );
      })}
    </select>
  );
}

export default Drop;
